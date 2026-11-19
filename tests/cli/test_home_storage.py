"""Home defaults are resolved at command time without inspection side effects."""

from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from harborist.cli import app
from harborist.domain import RunContract
from harborist.persistence import FileRunStore
from tests.git_helpers import git, init_repository
from tests.settings_helpers import write_settings


@pytest.mark.parametrize("command", ["inspect", "methodology"])
@pytest.mark.parametrize("existing_root", [False, True])
def test_missing_inspection_is_actionable_and_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, existing_root: bool
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    root = home / ".harborist" / "runs"
    if existing_root:
        root.mkdir(parents=True)
    run_id = uuid4()
    result = CliRunner().invoke(app, [command, str(run_id)])
    assert result.exit_code == 1
    assert str(root) in result.stderr
    assert str(run_id) in result.stderr
    assert "--runs-dir" in result.stderr
    assert root.exists() == existing_root
    assert not (root / str(run_id)).exists()
    assert not (home / ".harborist" / "workspaces").exists()


def test_intake_default_and_historical_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    target = tmp_path / "project"
    init_repository(target)
    (target / "harborist.yaml").write_text(
        "version: 1\nchecks: [{id: test, command: 'true'}]\n"
    )
    git(target, "add", ".")
    git(target, "commit", "-m", "base")
    issue = tmp_path / "issue.md"
    issue.write_text("Implement")
    settings = write_settings(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = CliRunner().invoke(
        app,
        [
            "intake",
            "--json",
            f"file:{issue}",
            "--settings",
            str(settings),
            "--repo",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    contract = RunContract.model_validate_json(result.stdout)
    directory = home / ".harborist" / "runs" / str(contract.run_id)
    assert (directory / "execution-context.json").is_file()
    # Historical captures need no locator; inspection must not add one back.
    (directory / "execution-context.json").unlink()
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    for command in ("inspect", "methodology"):
        inspected = CliRunner().invoke(app, [command, str(contract.run_id)])
        assert inspected.exit_code == 0, inspected.output
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}
    assert not (target / ".harborist").exists()
    assert not (elsewhere / ".harborist").exists()


@pytest.mark.parametrize("kind", ["file", "permission"])
def test_runs_storage_failure_identifies_path_and_remedy(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    root = tmp_path / "data" / "runs"
    if kind == "file":
        root.parent.write_text("preserve")
    else:
        original = Path.mkdir

        def denied(
            self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
        ) -> None:
            if self == root:
                raise PermissionError("access denied")
            original(self, mode=mode, parents=parents, exist_ok=exist_ok)

        monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(ValueError) as caught:
        FileRunStore(root=root).save(frozen_contract)
    assert str(root) in str(caught.value)
    assert "--runs-dir" in str(caught.value)
    if kind == "file":
        assert root.parent.read_text() == "preserve"
    else:
        assert "access denied" in str(caught.value)


def test_projects_share_home_storage_with_distinct_workspaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harborist.agents import codex
    from tests.application.test_run_execution import FakeAgent

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(codex, "CodexAgent", FakeAgent)
    issue = tmp_path / "issue.md"
    issue.write_text("Implement")
    settings = write_settings(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    captures: dict[Path, dict[str, bytes]] = {}
    run_ids: set[object] = set()
    for name in ("first", "second"):
        target = tmp_path / name
        init_repository(target)
        (target / "project.txt").write_text(name)
        (target / "harborist.yaml").write_text(
            "version: 1\nchecks: [{id: test, command: 'test -f requested.txt'}]\n"
        )
        git(target, "add", ".")
        git(target, "commit", "-m", name)
        result = CliRunner().invoke(
            app,
            [
                "intake",
                "--json",
                f"file:{issue}",
                "--settings",
                str(settings),
                "--repo",
                str(target),
            ],
        )
        assert result.exit_code == 0, result.output
        contract = RunContract.model_validate_json(result.stdout)
        assert contract.run_id not in run_ids
        run_ids.add(contract.run_id)
        directory = home / ".harborist" / "runs" / str(contract.run_id)
        # Also exercise historical execution without a saved locator.
        (directory / "execution-context.json").unlink()
        executed = CliRunner().invoke(
            app, ["run", "--foreground", str(contract.run_id), "--repo", str(target)]
        )
        assert executed.exit_code == 0, executed.output
        workspace = home / ".harborist" / "runs" / str(contract.run_id) / "workspace"
        assert (workspace / "project.txt").read_text() == name
        assert not (target / "requested.txt").exists()
        assert not (target / ".harborist").exists()
        for artifact in (
            "contract.json",
            "run.json",
            "attempt.json",
            "events.jsonl",
            "timing.json",
            "stage-timings.json",
            "report.md",
            "evidence.json",
            "design/spec.md",
            "plan/plan.md",
            "build/manifest.json",
            "test/manifest.json",
            "review/review.md",
        ):
            assert (directory / artifact).is_file(), artifact
        captures[directory] = {
            str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob("*")
            if p.is_file()
        }
    for directory, before in captures.items():
        assert before == {
            str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob("*")
            if p.is_file()
        }
