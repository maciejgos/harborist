"""Invocation locators and real POSIX-shell capture/execute compatibility."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from shipyard.agents import codex
from shipyard.application.context import ExecutionContext
from shipyard.cli import app
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture
from tests.git_helpers import git, init_repository
from tests.settings_helpers import write_settings


@pytest.mark.parametrize("layout", ["default", "external", "inside"])
def test_emitted_command_executes_from_another_cwd_via_posix_shell(
    tmp_path: Path, layout: str
) -> None:
    # The installed entry point is replaced only at the native-agent boundary.
    project = Path(__file__).resolve().parents[2]
    binary = tmp_path / "bin"
    binary.mkdir()
    entry = binary / "shipyard"
    entry.write_text(
        f"#!{sys.executable}\n"
        "from shipyard.agents import codex\n"
        "from tests.application.test_run_execution import FakeAgent\n"
        "codex.CodexAgent = lambda: FakeAgent('clarify')\n"
        "from shipyard.cli import app\n"
        "app()\n"
    )
    entry.chmod(0o755)
    target = tmp_path / "target with 'quotes' and $dollars;"
    init_repository(target)
    (target / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: test, command: 'true'}]\n"
    )
    git(target, "add", ".")
    git(target, "commit", "-m", "base")
    frozen = git(target, "rev-parse", "HEAD")
    issue = tmp_path / "issue.md"
    issue.write_text("Implement")
    settings = write_settings(tmp_path)
    home = tmp_path / "home with 'quotes' and $(touch bad);"
    home.mkdir()
    runs = {
        "default": home / ".shipyard" / "runs",
        "external": tmp_path / "runs with 'quotes' and $(touch bad);",
        "inside": target / ".shipyard" / "runs",
    }[layout]
    environment = {
        **os.environ,
        "HOME": str(home),
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": os.pathsep.join([str(project / "src"), str(project)]),
    }
    args = [
        "shipyard",
        "intake",
        f"file:{issue}",
        "--repo",
        str(target),
        "--settings",
        str(settings),
    ]
    if layout != "default":
        args += ["--runs-dir", str(runs)]
    intake = subprocess.run(
        args, env=environment, capture_output=True, text=True, check=False
    )
    assert intake.returncode == 0, intake.stderr
    directory = next(runs.iterdir())
    contract = RunContract.model_validate_json(
        (directory / "contract.json").read_text()
    )
    command = intake.stdout.split("Execute:\n", 1)[1].strip()
    assert intake.stderr == ""
    assert shlex.split(command) == [
        "shipyard",
        "run",
        str(contract.run_id),
        "--context",
        str(runs / str(contract.run_id) / "execution-context.json"),
    ]
    # Advancing HEAD must never change the base used by the emitted command.
    git(target, "commit", "--allow-empty", "-m", "after intake")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    executed = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=elsewhere,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert executed.returncode == 2, executed.stderr
    payload = json.loads(executed.stdout)
    assert payload["run"]["outcome"] == "NEEDS_CLARIFICATION"
    assert Path(payload["report"]) == runs / str(contract.run_id) / "report.md"
    # Use Git's own worktree records to check the retained destination and SHA.
    records = git(target, "worktree", "list", "--porcelain").split("\n\n")
    linked = next(record for record in records if "detached" in record)
    workspace = Path(linked.splitlines()[0].removeprefix("worktree "))
    assert workspace == home / ".shipyard" / "workspaces" / str(contract.run_id)
    assert workspace.is_dir()
    assert not workspace.resolve().is_relative_to(target.resolve())
    assert git(workspace, "rev-parse", "HEAD") == frozen == contract.base_sha
    assert not (elsewhere / "bad").exists()


@pytest.mark.parametrize(
    "kind", ["missing", "unreadable", "json", "schema", "version", "run", "location"]
)
def test_bad_context_fails_before_admission(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    locator = ExecutionContext(
        version=1,
        run_id=contract.run_id,
        repository=(tmp_path / "repository").resolve(),
        runs_root=(tmp_path / "runs").resolve(),
    )
    path = locator.save()
    if kind == "missing":
        path.unlink()
    elif kind == "unreadable":
        original = Path.read_bytes

        def unreadable(self: Path) -> bytes:
            if self == path:
                raise PermissionError("denied")
            return original(self)

        monkeypatch.setattr(Path, "read_bytes", unreadable)
    elif kind == "json":
        path.write_text("{")
    elif kind == "schema":
        data = locator.model_dump(mode="json")
        del data["version"]
        path.write_text(json.dumps(data))
    elif kind == "version":
        path.write_text(locator.model_dump_json().replace('"version":1', '"version":2'))
    elif kind == "run":
        path.write_text(
            locator.model_copy(update={"run_id": uuid4()}).model_dump_json()
        )
    else:
        moved = tmp_path / "moved.json"
        path.rename(moved)
        path = moved
    directory = store.directory(contract.run_id)
    before = (directory / "run.json").read_bytes()
    agent = FakeAgent("clarify")
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    result = CliRunner().invoke(
        app, ["run", str(contract.run_id), "--context", str(path)]
    )
    assert result.exit_code == 1, result.output
    assert "--context" in result.stderr and str(path) in result.stderr
    assert "explicit --repo and --runs-dir" in result.stderr
    assert agent.calls == []
    assert (directory / "run.json").read_bytes() == before
    assert not (directory / ".execution").exists()


@pytest.mark.parametrize("option", ["--repo", "--runs-dir"])
def test_context_rejects_explicit_conflicts(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    option: str,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    path = ExecutionContext(
        version=1,
        run_id=contract.run_id,
        repository=(tmp_path / "repository").resolve(),
        runs_root=(tmp_path / "runs").resolve(),
    ).save()
    other = tmp_path / "other"
    init_repository(other)
    agent = FakeAgent("clarify")
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    result = CliRunner().invoke(
        app, ["run", str(contract.run_id), "--context", str(path), option, str(other)]
    )
    assert result.exit_code == 1
    assert f"Conflicting {option}" in result.stderr
    assert "expected" in result.stderr
    assert not (store.directory(contract.run_id) / ".execution").exists()
    assert agent.calls == []


def test_matching_aliases_and_explicit_workspace_are_supported(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    repository = (tmp_path / "repository").resolve()
    runs = (tmp_path / "runs").resolve()
    path = ExecutionContext(
        version=1, run_id=contract.run_id, repository=repository, runs_root=runs
    ).save()
    alias = tmp_path / "alias"
    alias.symlink_to(repository, target_is_directory=True)
    subdir = repository / "subdir"
    subdir.mkdir()
    runs_alias = tmp_path / "runs-alias"
    runs_alias.symlink_to(runs, target_is_directory=True)
    workspace = tmp_path / "explicit workspace"
    monkeypatch.setattr(codex, "CodexAgent", lambda: FakeAgent("clarify"))
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(contract.run_id),
            "--context",
            str(path),
            "--repo",
            str(alias / "subdir"),
            "--runs-dir",
            str(runs_alias),
            "--workspace",
            str(workspace),
        ],
    )
    assert result.exit_code == 2, result.output
    assert workspace.is_dir()
    assert store.load(contract.run_id) == contract


def test_context_is_create_only(tmp_path: Path) -> None:
    run_id = uuid4()
    (tmp_path / str(run_id)).mkdir()
    locator = ExecutionContext(
        version=1,
        run_id=run_id,
        repository=tmp_path.resolve(),
        runs_root=tmp_path.resolve(),
    )
    path = locator.save()
    before = path.read_bytes()
    with pytest.raises(ValueError, match="capture .* is retained"):
        locator.save()
    assert path.read_bytes() == before
