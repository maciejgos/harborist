"""Combined capture/execution across real Git and fake external boundaries."""

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shipyard.cli import app
from tests.git_helpers import git, init_repository
from tests.settings_helpers import write_settings

runner = CliRunner()


@pytest.fixture
def target(tmp_path: Path) -> Path:
    path = tmp_path / "target"
    init_repository(path)
    (path / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: test, command: 'test -f requested.txt'}]\n"
    )
    git(path, "add", ".")
    git(path, "commit", "-m", "base")
    write_settings(path).rename(path / "shipyard.settings.yaml")
    return path


@pytest.mark.parametrize("command", ["intake", "run"])
@pytest.mark.parametrize(
    "failure,remedy",
    [
        (FileNotFoundError("gh"), "install"),
        (subprocess.CalledProcessError(1, ["gh"], stderr=b"secret"), "gh auth login"),
        (subprocess.TimeoutExpired(["gh"], 30), "retry"),
        (b'{"body":"secret"}', "invalid response"),
    ],
)
def test_github_capture_failure_is_actionable(
    tmp_path: Path,
    target: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception | bytes,
    remedy: str,
    command: str,
) -> None:
    from shipyard.agents import codex
    from shipyard.application import execution
    from shipyard.intake import github

    original = subprocess.run

    def transport(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        if args[0] != "gh":
            return original(args, **kwargs)  # type: ignore[arg-type]
        if isinstance(failure, Exception):
            raise failure
        return subprocess.CompletedProcess(args, 0, failure)

    def forbidden(**kwargs: object) -> None:
        pytest.fail("Capture failure must not execute")

    monkeypatch.setattr(github.subprocess, "run", transport)
    monkeypatch.setattr(execution, "execute_run", forbidden)
    monkeypatch.setattr(codex, "CodexAgent", forbidden)
    result = runner.invoke(
        app,
        [
            command,
            "github:source/repository#7",
            "--repo",
            str(target),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "github:source/repository#7" in result.stderr
    assert remedy in result.stderr.lower()
    assert "secret" not in result.stderr
    assert not list((tmp_path / "runs").glob("*/contract.json"))


@pytest.mark.parametrize(
    "argument,options,explanation",
    [
        ("file:", [], "file:<nonempty-path>"),
        ("github:owner/repo#0", [], "positive-issue-number"),
        ("github:owner/repo#1x", [], "positive-issue-number"),
        ("not-a-uuid", [], "UUID"),
        ("https://example.org/issue", [], "UUID"),
        ("file:issue.md", ["--context", "context.json"], "existing Run"),
        (
            "00000000-0000-0000-0000-000000000001",
            ["--settings", "x.yaml"],
            "source capture",
        ),
        ("00000000-0000-0000-0000-000000000001", ["--ref", "HEAD"], "source capture"),
        (
            "00000000-0000-0000-0000-000000000001",
            ["--timeout", "1800"],
            "source capture",
        ),
        (
            "00000000-0000-0000-0000-000000000001",
            ["--verification-reserve", "300"],
            "source capture",
        ),
    ],
)
def test_dispatch_rejects_before_application_calls(
    monkeypatch: pytest.MonkeyPatch, argument: str, options: list[str], explanation: str
) -> None:
    from shipyard.application import capture as application_capture
    from shipyard.application import execution

    def forbidden(**kwargs: object) -> None:
        pytest.fail("Invalid invocation must not capture or execute")

    monkeypatch.setattr(application_capture, "create_run", forbidden)
    monkeypatch.setattr(execution, "execute_run", forbidden)
    result = runner.invoke(app, ["run", "--foreground", argument, *options])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert explanation in result.stderr


@pytest.mark.parametrize("source_kind", ["file", "github"])
def test_combined_path_captures_once_and_executes_frozen_snapshot(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch, source_kind: str
) -> None:
    import json

    from shipyard.agents import codex
    from shipyard.application import capture as application_capture
    from shipyard.application.execution import execute_run
    from shipyard.domain import RunContract
    from shipyard.intake import github
    from shipyard.persistence import FileRunStore
    from tests.application.test_run_execution import FakeAgent

    issue = tmp_path / "issue.md"
    issue.write_text("Implement requested.txt")
    source = f"file:{issue}" if source_kind == "file" else "github:unrelated/source#7"
    reads = 0
    fetches = 0
    captures: list[RunContract] = []
    executions: list[object] = []
    original_read = Path.read_bytes
    original_transport = subprocess.run
    original_create = application_capture.create_run

    def read(self: Path) -> bytes:
        nonlocal reads
        if self == issue:
            reads += 1
        return original_read(self)

    def transport(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal fetches
        if args[0] != "gh":
            return original_transport(args, **kwargs)  # type: ignore[arg-type]
        fetches += 1
        assert args[args.index("--repo") + 1] == "unrelated/source"
        return subprocess.CompletedProcess(
            args, 0, b'{"title":"Task","body":"Implement requested.txt","labels":[]}'
        )

    def capture_once(**kwargs: object) -> RunContract:
        contract = original_create(**kwargs)  # type: ignore[arg-type]
        captures.append(contract)
        issue.unlink()
        (target / "shipyard.settings.yaml").unlink()
        return contract

    def execute_once(**kwargs: object):  # type: ignore[no-untyped-def]
        executions.append(kwargs["run_id"])
        assert captures[0].run_id == kwargs["run_id"]
        assert (
            FileRunStore(root=tmp_path / "runs").load(captures[0].run_id) == captures[0]
        )
        return execute_run(**kwargs)  # type: ignore[arg-type]

    agent = FakeAgent()
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(github.subprocess, "run", transport)
    monkeypatch.setattr(application_capture, "create_run", capture_once)
    monkeypatch.setattr("shipyard.application.execution.execute_run", execute_once)
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    nested = target / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    base = git(target, "rev-parse", "HEAD")
    result = runner.invoke(
        app,
        [
            "run",
            "--foreground",
            source,
            "--runs-dir",
            str(tmp_path / "runs"),
            "--ref",
            base,
            "--timeout",
            "900",
            "--verification-reserve",
            "100",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["run"]["outcome"] == "VERIFIED"
    (contract,) = captures
    assert executions == [contract.run_id]
    assert reads == (1 if source_kind == "file" else 0)
    assert fetches == (1 if source_kind == "github" else 0)
    assert contract.base_sha == base
    assert contract.execution.budget.total_seconds == 900
    assert contract.execution.budget.verification_reserve_seconds == 100
    (directory,) = (tmp_path / "runs").iterdir()
    assert (directory / "intent.md").read_text().endswith("Implement requested.txt")
    assert (directory / "execution-context.json").is_file()
    assert (directory / "workspace-layout.json").is_file()
    assert Path(payload["workspace"]) == directory / "workspace"
    assert str(contract.run_id) in result.stderr
    assert "Captured Run" in result.stderr
    assert "Execute:" not in result.output
    assert agent.calls


def test_preflight_failure_retains_capture_and_recovers_without_live_inputs(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shlex

    from shipyard.agents import codex
    from shipyard.persistence import FileRunStore
    from tests.application.test_run_execution import FakeAgent

    issue = tmp_path / "issue.md"
    issue.write_text("Implement requested.txt")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runs = target / "runs with 'quotes' and $dollars;"
    agent = FakeAgent("clarify")
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    result = runner.invoke(
        app,
        [
            "run",
            "--foreground",
            f"file:{issue}",
            "--repo",
            str(target),
            "--runs-dir",
            str(runs),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    (directory,) = runs.iterdir()
    from uuid import UUID

    run_id = UUID(directory.name)
    store = FileRunStore(root=runs)
    before = store.load(run_id)
    assert store.load_state(run_id).lifecycle.value == "CREATED"
    assert agent.calls == []
    assert "fresh external --workspace" in result.stderr
    command = shlex.split(result.stderr.split("Recover with:\n", 1)[1].splitlines()[0])
    assert command[:3] == ["shipyard", "run", str(run_id)]
    assert command[3:5] == ["--runs-dir", str(runs)]
    issue.unlink()
    (target / "shipyard.settings.yaml").unlink()
    recovered = runner.invoke(app, command[1:])
    assert recovered.exit_code == 2, recovered.output
    assert "NEEDS_CLARIFICATION" in recovered.stdout
    assert store.load(run_id) == before
    assert list(runs.iterdir()) == [directory]
    assert agent.calls


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
def test_file_capture_failure_has_correction_and_no_run(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from shipyard.agents import codex

    issue = tmp_path / "missing.md"
    if failure == "unreadable":
        issue.write_text("Implement")
        original = Path.read_bytes

        def denied(self: Path) -> bytes:
            if self == issue:
                raise PermissionError("denied")
            return original(self)

        monkeypatch.setattr(Path, "read_bytes", denied)

    def forbidden() -> None:
        pytest.fail("Capture failure must not construct an agent")

    monkeypatch.setattr(codex, "CodexAgent", forbidden)
    result = runner.invoke(
        app,
        [
            "run",
            "--foreground",
            f"file:{issue}",
            "--repo",
            str(target),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert str(issue) in result.stderr
    assert "Check the path" in result.stderr
    assert not list((tmp_path / "runs").glob("*/contract.json"))


@pytest.mark.parametrize(
    "mode,status", [("clarify", 2), ("failure", 1), ("cancel", 130)]
)
def test_admitted_source_outcomes_retain_evidence_without_recovery(
    tmp_path: Path,
    target: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    status: int,
) -> None:
    from shipyard.agents import codex
    from tests.application.test_run_execution import FakeAgent

    agent = FakeAgent(mode)
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    issue = tmp_path / "issue.md"
    issue.write_text("Implement")
    result = runner.invoke(
        app,
        [
            "run",
            "--foreground",
            f"file:{issue}",
            "--repo",
            str(target),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == status, result.output
    assert "Captured Run:" in result.stderr
    assert "Report:" in result.stdout
    assert "Evidence:" in result.stdout
    assert "Recover with:" not in result.stderr
    assert "Execute:" not in result.output
    (directory,) = (tmp_path / "runs").iterdir()
    assert (directory / "evidence.json").is_file()
    assert len(agent.calls) == 1


@pytest.mark.parametrize(
    "selection", ["relative-override", "invalid-default", "invalid-override", "budget"]
)
def test_source_configuration_selection(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    from shipyard.agents import codex
    from shipyard.domain import RunContract
    from tests.application.test_run_execution import FakeAgent

    agent = FakeAgent("clarify")
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    issue = tmp_path / "issue.md"
    issue.write_text("Implement")
    override = write_settings(tmp_path)
    monkeypatch.chdir(tmp_path)
    options: list[str] = []
    if selection in {"relative-override", "invalid-override"}:
        options = ["--settings", override.name]
    if selection == "invalid-override":
        override.write_text("invalid")
    if selection in {"relative-override", "invalid-default"}:
        (target / "shipyard.settings.yaml").write_text("invalid")
    if selection == "budget":
        options = ["--timeout", "100", "--verification-reserve", "100"]
    workspace = tmp_path / "custom workspace"
    result = runner.invoke(
        app,
        [
            "run",
            "--foreground",
            f"file:{issue}",
            "--repo",
            str(target),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--workspace",
            str(workspace),
            *options,
        ],
    )
    if selection == "relative-override":
        assert result.exit_code == 2, result.output
        (directory,) = (tmp_path / "runs").iterdir()
        contract = RunContract.model_validate_json(
            (directory / "contract.json").read_bytes()
        )
        assert contract.execution.agent_profile.model == "operator-selected-model"
        assert workspace.is_dir()
    else:
        assert result.exit_code == 1, result.output
        assert result.stdout == ""
        assert agent.calls == []
        assert not list((tmp_path / "runs").glob("*/contract.json"))
        if selection != "budget":
            assert "--settings PATH" in result.stderr


def test_run_help_documents_both_modes() -> None:
    result = runner.invoke(app, ["run", "--help"])
    text = " ".join(result.stdout.split())
    for phrase in (
        "source",
        "UUID",
        "--settings",
        "--ref",
        "--timeout",
        "--verification-reserve",
        "--context",
        "CREATED",
        "--workspace",
        "shipyard.settings.yaml",
    ):
        assert phrase in text
