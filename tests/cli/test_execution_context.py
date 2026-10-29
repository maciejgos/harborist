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
from shipyard.persistence import FileRunStore
from tests.application.test_run_execution import FakeAgent, capture
from tests.git_helpers import git, init_repository
from tests.settings_helpers import write_settings


@pytest.mark.parametrize("layout", ["default", "external", "inside"])
@pytest.mark.parametrize("json_hint", [False, True])
def test_emitted_command_executes_from_another_cwd_via_posix_shell(
    tmp_path: Path, layout: str, json_hint: bool
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
    if json_hint:
        args += ["--json"]
    intake = subprocess.run(
        args, env=environment, capture_output=True, text=True, check=False
    )
    assert intake.returncode == 0, intake.stderr
    directory = next(runs.iterdir())
    contract = RunContract.model_validate_json(
        (directory / "contract.json").read_text()
    )
    command = (
        intake.stderr.strip()
        if json_hint
        else intake.stdout.split("Execute:\n", 1)[1].strip()
    )
    if json_hint:
        assert RunContract.model_validate_json(intake.stdout) == contract
    else:
        assert intake.stderr == ""
    assert shlex.split(command) == [
        "shipyard",
        "run",
        str(contract.run_id),
    ] + (["--runs-dir", str(runs)] if layout != "default" else [])
    if layout != "external":
        command += " --json"
    # Advancing HEAD must never change the base used by the emitted command.
    git(target, "commit", "--allow-empty", "-m", "after intake")
    elsewhere = tmp_path / "elsewhere"
    if layout == "external":
        init_repository(elsewhere)
    else:
        elsewhere.mkdir()
    executed = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=elsewhere,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    expected_workspace = runs / str(contract.run_id) / "workspace"
    if layout == "inside":
        assert executed.returncode == 1, executed.stderr
        assert str(expected_workspace) in executed.stderr
        assert "--workspace" in executed.stderr
        assert (
            FileRunStore(root=runs).load_state(contract.run_id).lifecycle.value
            == "CREATED"
        )
        assert not (directory / ".execution").exists()
        expected_workspace = tmp_path / "fresh external checkout"
        executed = subprocess.run(
            [
                "/bin/sh",
                "-c",
                command + " --workspace " + shlex.quote(str(expected_workspace)),
            ],
            cwd=elsewhere,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    assert executed.returncode == 2, executed.stderr
    if layout == "external":
        assert "Status: COMPLETED" in executed.stdout
        assert "Result: NEEDS_CLARIFICATION" in executed.stdout
        assert f"Report: {directory.resolve() / 'report.md'}" in executed.stdout
        assert f"Evidence: {directory.resolve() / 'evidence.json'}" in executed.stdout
    else:
        payload = json.loads(executed.stdout)
        assert payload["run"]["outcome"] == "NEEDS_CLARIFICATION"
        assert Path(payload["report"]) == runs / str(contract.run_id) / "report.md"
    # Use Git's own worktree records to check the retained destination and SHA.
    records = git(target, "worktree", "list", "--porcelain").split("\n\n")
    linked = next(record for record in records if "detached" in record)
    workspace = Path(linked.splitlines()[0].removeprefix("worktree "))
    assert workspace == expected_workspace
    assert workspace.is_dir()
    assert not workspace.resolve().is_relative_to(target.resolve())
    assert git(workspace, "rev-parse", "HEAD") == frozen == contract.base_sha
    assert not (elsewhere / "bad").exists()


@pytest.mark.parametrize(
    "kind,automatic",
    [
        (kind, automatic)
        for kind in [
            "missing",
            "unreadable",
            "json",
            "schema",
            "version",
            "run",
            "location",
            "directory",
            "dangling",
            "relative",
        ]
        for automatic in [False, True]
        if (kind, automatic) != ("missing", True)
    ],
)
def test_bad_context_fails_before_admission(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    automatic: bool,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    locator = ExecutionContext(
        version=1,
        run_id=contract.run_id,
        repository=(tmp_path / "repository").resolve(),
        runs_root=(tmp_path / "runs").resolve(),
    )
    path = locator.save()
    read_bytes = Path.read_bytes
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
    elif kind == "directory":
        path.unlink()
        path.mkdir()
    elif kind == "dangling":
        path.unlink()
        path.symlink_to(tmp_path / "absent")
    elif kind == "relative":
        path.write_text(
            locator.model_dump_json().replace(str(locator.repository), "relative")
        )
    else:
        moved = tmp_path / "moved.json"
        path.rename(moved)
        if automatic:
            path.write_bytes(
                moved.read_bytes().replace(
                    str(locator.runs_root).encode(), str(tmp_path / "wrong").encode()
                )
            )
        else:
            path = moved
    directory = store.directory(contract.run_id)
    before = {p.name: read_bytes(p) for p in directory.iterdir() if p.is_file()}
    agent = FakeAgent("clarify")
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    result = CliRunner().invoke(
        app,
        ["run", str(contract.run_id)]
        + (
            ["--runs-dir", str(locator.runs_root)]
            if automatic
            else ["--context", str(path)]
        ),
    )
    assert result.exit_code == 1, result.output
    assert str(path) in result.stderr
    assert "Invalid" in result.stderr
    assert "omit --context" not in result.stderr
    assert "legacy explicit invocation" not in result.stderr
    assert agent.calls == []
    assert {p.name: read_bytes(p) for p in directory.iterdir() if p.is_file()} == before
    assert list(store.directory(contract.run_id).parent.iterdir()) == [directory]
    assert not (directory / ".execution").exists()


@pytest.mark.parametrize(
    "option,automatic", [("--repo", False), ("--repo", True), ("--runs-dir", False)]
)
def test_context_rejects_explicit_conflicts(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    option: str,
    automatic: bool,
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
    if automatic:
        monkeypatch.setattr("shipyard.cli.runs_root", lambda: path.parent.parent)
    arguments = ["run", str(contract.run_id)]
    if not automatic:
        arguments += ["--context", str(path)]
    result = CliRunner().invoke(app, arguments + [option, str(other)])
    assert result.exit_code == 1
    assert f"Conflicting {option}" in result.stderr
    assert "expected" in result.stderr
    assert not (store.directory(contract.run_id) / ".execution").exists()
    assert agent.calls == []


@pytest.mark.parametrize("automatic", [False, True])
def test_matching_aliases_and_explicit_workspace_are_supported(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    automatic: bool,
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
            *([] if automatic else ["--context", str(path)]),
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


@pytest.mark.parametrize("explicit_valid", [False, True])
def test_explicit_context_alone_selects_locator(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    explicit_valid: bool,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    path = ExecutionContext(
        version=1,
        run_id=contract.run_id,
        repository=(tmp_path / "repository").resolve(),
        runs_root=store.directory(contract.run_id).parent.resolve(),
    ).save()
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    competing = home / ".shipyard" / "runs" / str(contract.run_id) / path.name
    competing.parent.mkdir(parents=True)
    competing.write_text("invalid automatic context")
    agent = FakeAgent("clarify")
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    selected = path if explicit_valid else tmp_path / "missing.json"
    result = CliRunner().invoke(
        app, ["run", str(contract.run_id), "--context", str(selected)]
    )
    assert result.exit_code == (2 if explicit_valid else 1), result.output
    assert bool(agent.calls) == explicit_valid
    assert competing.read_text() == "invalid automatic context"
    assert (store.directory(contract.run_id) / ".execution").exists() == explicit_valid


@pytest.mark.parametrize("selection", ["explicit", "cwd", "default"])
def test_absent_context_keeps_legacy_selection_without_backfill(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    repository = tmp_path / "repository"
    if selection == "default":
        monkeypatch.setattr(
            "shipyard.cli.runs_root", lambda: store.directory(contract.run_id).parent
        )
    if selection == "explicit":
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
    else:
        monkeypatch.chdir(repository)
    directory = store.directory(contract.run_id)
    frozen = {
        name: (directory / name).read_bytes()
        for name in (
            "contract.json",
            "intent.json",
            "intent.md",
            "workspace-layout.json",
        )
    }
    monkeypatch.setattr(codex, "CodexAgent", lambda: FakeAgent("clarify"))
    arguments = ["run", str(contract.run_id)]
    if selection != "default":
        arguments += ["--runs-dir", str(store.directory(contract.run_id).parent)]
    if selection == "explicit":
        arguments += ["--repo", str(repository)]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 2, result.output
    assert not (directory / "execution-context.json").exists()
    assert {name: (directory / name).read_bytes() for name in frozen} == frozen
    assert list(store.directory(contract.run_id).parent.iterdir()) == [directory]
