"""Deterministic target-root settings selection and immutable capture."""

import hashlib
import json
import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from shipyard.cli import app
from shipyard.configuration import load_execution_settings
from shipyard.domain import RunContract, RunOutcome
from shipyard.git import GitRepository
from shipyard.persistence import FileRunStore
from shipyard.sandbox.docker import DockerSandboxRuntime
from shipyard.skills import compile_methodology
from tests.application.test_run_execution import FakeAgent
from tests.cli.conftest import strip_ansi
from tests.git_helpers import git, init_repository
from tests.settings_helpers import write_settings

runner = CliRunner()


@pytest.fixture
def target(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    init_repository(target)
    (target / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: test, command: 'test -f requested.txt'}]\n"
    )
    git(target, "add", ".")
    git(target, "commit", "-m", "base")
    return target


def conventional(target: Path) -> Path:
    path = target / "shipyard.settings.yaml"
    write_settings(target).rename(path)
    return path


def invoke(tmp_path: Path, *options: str) -> Result:
    issue = tmp_path / "issue.md"
    issue.write_text("Implement requested.txt")
    return runner.invoke(
        app,
        ["intake", f"file:{issue}", "--runs-dir", str(tmp_path / "runs"), *options],
    )


@pytest.mark.parametrize("nested", [False, True])
def test_default_discovery_and_presentation(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch, nested: bool
) -> None:
    conventional(target)
    cwd = target / "nested" if nested else target
    cwd.mkdir(exist_ok=True)
    monkeypatch.chdir(cwd)
    result = invoke(tmp_path)
    assert result.exit_code == 0, result.output
    directory = next((tmp_path / "runs").iterdir())
    contract = RunContract.model_validate_json(
        (directory / "contract.json").read_bytes()
    )
    for value in (
        str(contract.run_id),
        str(target.resolve()),
        contract.base_sha,
        contract.intent.source_ref,
        "CREATED",
        "Run captured",
        "Execute:",
    ):
        assert value in result.stdout
    assert result.stderr == ""


def test_other_target_subdirectory_wins_over_caller_and_nested_files(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conventional(target)
    caller = tmp_path / "caller"
    init_repository(caller)
    conventional(caller).write_text("invalid caller")
    nested = target / "nested"
    nested.mkdir()
    (nested / "shipyard.settings.yaml").write_text("invalid nested")
    monkeypatch.chdir(caller)
    result = invoke(tmp_path, "--repo", str(nested), "--json")
    assert result.exit_code == 0, result.output
    contract = RunContract.model_validate_json(result.stdout)
    assert contract.execution == load_execution_settings(
        path=target / "shipyard.settings.yaml"
    )
    assert shlex.split(result.stderr) == [
        "shipyard",
        "run",
        str(contract.run_id),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]
    skill_bytes = (target / "skill.md").read_bytes()
    assert contract.execution.skills[0].content.encode() == skill_bytes
    assert (
        contract.execution.skills[0].sha256 == hashlib.sha256(skill_bytes).hexdigest()
    )


@pytest.mark.parametrize("default", ["missing", "invalid"])
def test_explicit_external_relative_override(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch, default: str
) -> None:
    if default == "invalid":
        conventional(target).write_text("invalid")
    explicit = write_settings(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = invoke(
        tmp_path, "--repo", str(target), "--settings", explicit.name, "--json"
    )
    assert result.exit_code == 0, result.output
    assert RunContract.model_validate_json(
        result.stdout
    ).execution == load_execution_settings(path=explicit)


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "yaml",
        "schema",
        "unreadable",
        "explicit",
        "methodology",
        "asset",
        "verification",
    ],
)
def test_selected_settings_failure_stops_before_capture(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import shipyard.intake.source as source_adapter

    path = conventional(target)
    options = ["--repo", str(target)]
    if failure == "missing":
        path.unlink()
        nested = target / "nested"
        nested.mkdir()
        conventional(nested)
        conventional(tmp_path)  # Caller configuration must not be a fallback.
    elif failure == "explicit":
        path = tmp_path / "override.yaml"
        path.write_text("invalid")
        options += ["--settings", str(path)]
    elif failure == "yaml":
        path.write_text("[")
    elif failure == "schema":
        path.write_text("version: 1\n")
    elif failure == "methodology":
        (target / "playbook.md").write_text("# Invalid methodology")
    elif failure == "asset":
        (target / "skill.md").unlink()
    elif failure == "verification":
        path.write_text(path.read_text() + "checks: [{id: bypass, command: 'true'}]\n")
    else:
        original = Path.read_bytes

        def denied(self: Path) -> bytes:
            if self == path:
                raise PermissionError("selected settings denied")
            return original(self)

        monkeypatch.setattr(Path, "read_bytes", denied)

    def forbidden(**kwargs: object) -> None:
        pytest.fail("Source capture must not start on settings failure")

    monkeypatch.setattr(source_adapter, "read_markdown_intent", forbidden)
    monkeypatch.chdir(tmp_path)
    result = invoke(tmp_path, *options)
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert str(path) in result.stderr
    assert "--settings PATH" in result.stderr
    assert not (tmp_path / "runs").exists()


def test_discovery_freezes_local_settings_and_base_checks_for_execution(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shipyard.configuration.execution as settings_module
    from shipyard.agents.base import AgentRequest, AgentResponse
    from shipyard.application import capture as application_capture
    from shipyard.application.execution import execute_run

    path = conventional(target)
    base = git(target, "rev-parse", "HEAD")
    (target / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: changed, command: 'false'}]\n"
    )
    git(target, "add", "shipyard.yaml")
    git(target, "commit", "-m", "new checks")
    (target / "shipyard.yaml").write_text("invalid live verification")
    result = invoke(tmp_path, "--repo", str(target), "--ref", base, "--json")
    assert result.exit_code == 0, result.output
    contract = RunContract.model_validate_json(result.stdout)
    assert contract.base_sha == base
    assert contract.verification.config.checks[0].command == "test -f requested.txt"
    store = FileRunStore(root=tmp_path / "runs")
    before = (store.directory(contract.run_id) / "contract.json").read_bytes()
    path.unlink()
    (target / "playbook.md").unlink()
    (target / "skill.md").write_text("changed live skill")
    assert store.load(contract.run_id).model_dump_json().encode() == before

    def forbidden(**kwargs: object) -> None:
        pytest.fail("Execution must not reload live settings")

    monkeypatch.setattr(application_capture, "load_execution_settings", forbidden)
    monkeypatch.setattr(settings_module, "load_execution_settings", forbidden)

    class FrozenAgent(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            assert request.profile == contract.execution.agent_profile
            assert (
                request.guidance.playbook.sha256 == contract.execution.playbook.sha256
            )
            if request.stage.value in {"design", "build"}:
                assert request.guidance.skills[0].content == "# Skill\r\n"
                assert (
                    request.guidance.skills[0].identity.sha256
                    == contract.execution.skills[0].sha256
                )
            return super().execute(request)

    agent = FrozenAgent()
    evidence = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=GitRepository(path=target),
        workspace=tmp_path / "work",
        agent=agent,
    )
    assert evidence.run.outcome == RunOutcome.VERIFIED
    assert agent.calls
    assert (store.directory(contract.run_id) / "contract.json").read_bytes() == before


def test_help_documents_selection_policy() -> None:
    result = runner.invoke(app, ["intake", "--help"])
    text = " ".join(strip_ansi(result.stdout).split())
    for value in (
        "shipyard.settings.yaml",
        "target checkout root",
        "precedence",
        "invocation directory",
        "beside",
        "--settings PATH",
    ):
        assert value in text


def test_repository_and_explicit_example_settings_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)

    def baseline_digest(_: DockerSandboxRuntime) -> str:
        return "a" * 64

    monkeypatch.setattr(DockerSandboxRuntime, "baseline_digest", baseline_digest)
    for path in (
        root / "shipyard.settings.yaml",
        root / "examples/intake/settings.yaml",
    ):
        snapshot = load_execution_settings(path=path)
        compiled = compile_methodology(snapshot)
        assert snapshot.agent_profile.model == "gpt-6.1-sol"
        assert compiled.playbook.identity.name == "bounded-repository-change"
        assert compiled.skills[0].identity.version == "2"


def test_agent_setup_changes_only_future_intake(tmp_path: Path, target: Path) -> None:
    path = conventional(target)
    options = ("--repo", str(target))
    first = invoke(tmp_path, *options, "--json")
    assert first.exit_code == 0, first.output
    captured = RunContract.model_validate_json(first.stdout)

    updated = runner.invoke(
        app,
        ["agent", "configure", *options, "--model", "new-model", "--effort", "high"],
    )
    assert updated.exit_code == 0, updated.output
    second = invoke(tmp_path, *options, "--json")
    assert second.exit_code == 0, second.output
    profile = RunContract.model_validate_json(second.stdout).execution.agent_profile
    assert profile.model == "new-model"
    assert profile.arguments == ("-c", 'model_reasoning_effort="high"')
    saved = FileRunStore(root=tmp_path / "runs").load(captured.run_id)
    assert saved.execution.agent_profile.model == "operator-selected-model"

    before = path.read_bytes()
    rejected = runner.invoke(
        app,
        ["agent", "configure", *options, "--model=--ephemeral"],
    )
    assert rejected.exit_code != 0
    assert path.read_bytes() == before


def test_agent_check_redacts_auth_and_profile_errors(
    tmp_path: Path, target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = conventional(target)
    path.write_text(
        path.read_text().replace("arguments: []", "arguments: [hidden-profile-value]")
    )
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\necho hidden-auth-output >&2\nexit 1\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path), prepend=":")
    result = runner.invoke(app, ["agent", "check", "--repo", str(target), "--json"])
    assert result.exit_code == 1
    diagnostics = json.loads(result.stdout)
    assert diagnostics["connection"]["status"] == "credentials_unavailable"
    assert diagnostics["profile"]["status"] == "invalid_profile"
    assert "hidden-" not in result.output
