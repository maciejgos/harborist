"""End-to-end orchestration with real Git/checks and a synthetic native agent."""

import json
from pathlib import Path

import pytest

from shipyard.agents.base import AgentExecutionError, AgentRequest, AgentResponse
from shipyard.application.budget import BudgetClock
from shipyard.application.execution import execute_run
from shipyard.domain import FailureReason, RunContract, RunOutcome
from shipyard.domain.stage_result import AgentStage
from shipyard.git import GitRepository
from shipyard.persistence import FileRunStore
from shipyard.verification.config import load_verification_config
from tests.git_helpers import git, init_repository


class FakeAgent:
    def __init__(
        self, mode: str = "verified", ticks: list[float] | None = None
    ) -> None:
        self.mode = mode
        self.calls: list[AgentStage] = []
        self.ticks = ticks

    def execute(self, request: AgentRequest) -> AgentResponse:
        self.calls.append(request.stage)
        if self.mode == "failure":
            raise AgentExecutionError("provider unavailable")
        if self.mode == "cancel":
            raise KeyboardInterrupt
        if self.mode == "invalid":
            return AgentResponse(returncode=0, output="bad JSON")
        if self.ticks is not None:
            self.ticks[0] += 2000
        result: dict[str, object] = {"stage": request.stage.value, "status": "ready"}
        artifact = None
        if request.stage == AgentStage.DESIGN:
            artifact = "# Spec\nAC-001: requested implementation exists\n"
            if self.mode == "clarify":
                result["status"] = "needs_clarification"
        elif request.stage == AgentStage.PLAN:
            artifact = "# Plan\nImplement requested.txt"
            if self.mode == "rescope":
                result["status"] = "needs_rescoping"
        elif request.stage == AgentStage.BUILD:
            (request.workspace / "requested.txt").write_text("implemented")
            if self.mode == "caches":
                (request.workspace / ".gitignore").write_text(
                    ".venv/\n.pytest_cache/\n"
                )
                (request.workspace / ".venv").mkdir()
                (request.workspace / ".venv" / "build-only").write_text("dependency")
        else:
            artifact = "# Independent review"
            assert request.candidate is not None
            result.update(
                candidate=request.candidate.model_dump(mode="json"),
                criteria=[
                    {
                        "criterion_id": "AC-001",
                        "status": "fail"
                        if self.mode == "changes"
                        else "unverified"
                        if self.mode == "unverified"
                        else "pass",
                    }
                ],
            )
        return AgentResponse(
            returncode=0,
            output=json.dumps(
                {
                    "result": result,
                    "artifact": artifact,
                    "plan_update": None,
                }
            ),
        )


def capture(
    tmp_path: Path, frozen_contract: RunContract, check: str = "test -f requested.txt"
) -> tuple[FileRunStore, GitRepository, RunContract]:
    repository = tmp_path / "repository"
    init_repository(repository)
    (repository / "shipyard.yaml").write_text(
        f"version: 1\nchecks:\n  - id: test\n    command: {check}\n"
    )
    git(repository, "add", ".")
    git(repository, "commit", "-m", "base")
    repo = GitRepository(path=repository)
    base = repo.resolve_base()
    contract = RunContract.model_validate(
        {
            **frozen_contract.model_dump(),
            "base_sha": base,
            "verification": load_verification_config(repository=repo, base_sha=base),
        },
    )
    store = FileRunStore(root=tmp_path / "runs")
    store.save(contract)
    return store, repo, contract


@pytest.mark.parametrize(
    "tail,expected",
    [
        ("true", RunOutcome.VERIFIED),
        ("exit 1", RunOutcome.TEST_FAILED),
        ("echo changed >> requested.txt", RunOutcome.TEST_FAILED),
        ("touch unexpected.txt", RunOutcome.TEST_FAILED),
    ],
)
def test_disposable_caches_do_not_block_publication_or_verification(
    tmp_path: Path, frozen_contract: RunContract, tail: str, expected: RunOutcome
) -> None:
    # TEST must start without BUILD's environment; its own ignored cache is disposable.
    check = (
        "test ! -d .venv || exit 9; "
        "mkdir .pytest_cache && touch .pytest_cache/check && " + tail
    )
    store, repo, contract = capture(tmp_path, frozen_contract, check)
    agent = FakeAgent("caches")
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
    )
    assert result.run.outcome == expected
    assert result.candidate is not None
    assert not (tmp_path / "work" / ".venv").exists()
    assert not (tmp_path / "work" / ".pytest_cache").exists()
    assert (AgentStage.REVIEW in agent.calls) == (expected == RunOutcome.VERIFIED)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("verified", "VERIFIED"),
        ("clarify", "NEEDS_CLARIFICATION"),
        ("rescope", "NEEDS_RESCOPING"),
        ("changes", "CHANGES_REQUIRED"),
        ("unverified", "CHANGES_REQUIRED"),
        ("failure", "EXECUTION_FAILED"),
        ("invalid", "INVALID_STAGE_OUTPUT"),
        ("cancel", "CANCELLED"),
    ],
)
def test_terminal_results_always_package(
    tmp_path: Path, frozen_contract: RunContract, mode: str, expected: str
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    agent = FakeAgent(mode)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
    )
    assert (
        str(result.run.outcome or result.run.failure_reason or result.run.lifecycle)
        == expected
    )
    directory = tmp_path / "runs" / str(contract.run_id)
    assert expected in (directory / "report.md").read_text()
    assert store.load(contract.run_id) == contract
    assert store.load_state(contract.run_id) == result.run
    assert (directory / "events.jsonl").exists()
    if expected == "VERIFIED":
        assert result.candidate is not None
        assert result.run.verification is not None
        assert result.run.verification.candidate == result.candidate
        assert agent.calls == list(AgentStage)
    before = {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError):
        execute_run(
            store=store,
            run_id=contract.run_id,
            repository=repo,
            workspace=tmp_path / "other",
            agent=agent,
        )
    assert before == {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }


def test_failed_test_blocks_review_and_packages(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract, "exit 1")
    agent = FakeAgent()
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
    )
    assert result.run.outcome == RunOutcome.TEST_FAILED
    assert AgentStage.REVIEW not in agent.calls
    assert result.test is not None


def test_exhaustion_packages_without_another_executor(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    ticks = [0.0]
    clock = BudgetClock(contract.execution.budget, monotonic=lambda: ticks[0])
    agent = FakeAgent(ticks=ticks)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
        clock=clock,
    )
    assert result.run.failure_reason == FailureReason.TIME_BUDGET_EXCEEDED
    assert agent.calls == [AgentStage.DESIGN]
    assert result.timing.remaining_seconds == 0
    assert result.package_timing.remaining_seconds == 0
    assert result.package_timing.stage is not None
    assert result.package_timing.stage.value == "package"
    assert result.stage_timings[0].duration_seconds == 2000


def test_cli_runs_capture_and_returns_report_paths(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from shipyard.agents import codex
    from shipyard.cli import app

    store, _, contract = capture(tmp_path, frozen_contract)
    agent = FakeAgent()
    monkeypatch.setattr(codex, "CodexAgent", lambda: agent)
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--json",
            str(contract.run_id),
            "--repo",
            str(tmp_path / "repository"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--workspace",
            str(tmp_path / "work"),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert Path(payload["report"]).is_file()
    assert store.load_state(contract.run_id).outcome == RunOutcome.VERIFIED


def test_lifecycle_journal_tampering_fails_closed(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent("clarify"),
    )
    journal = store.directory(contract.run_id) / "events.jsonl"
    lines = journal.read_text().splitlines()
    journal.write_text("\n".join([lines[0], lines[-1], lines[1]]) + "\n")
    with pytest.raises(ValueError, match="lifecycle"):
        store.load_state(contract.run_id)


def test_unexpected_agent_error_still_packages(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    class BrokenAgent:
        def execute(self, request: AgentRequest) -> AgentResponse:
            raise LookupError("unexpected adapter failure")

    store, repo, contract = capture(tmp_path, frozen_contract)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=BrokenAgent(),
    )
    assert result.run.failure_reason == FailureReason.INTERNAL_ERROR
    assert result.error is not None and "LookupError" in result.error


def test_package_failure_is_surfaced_after_terminal_persistence(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shipyard.application import execution

    def unavailable(**kwargs: object) -> None:
        raise OSError("disk full during PACKAGE")

    store, repo, contract = capture(tmp_path, frozen_contract)
    monkeypatch.setattr(execution, "package_run", unavailable)
    with pytest.raises(OSError, match="disk full"):
        execute_run(
            store=store,
            run_id=contract.run_id,
            repository=repo,
            workspace=tmp_path / "work",
            agent=FakeAgent("clarify"),
        )
    assert store.load_state(contract.run_id).outcome == RunOutcome.NEEDS_CLARIFICATION


def test_terminal_verification_cannot_move_to_another_frozen_contract(
    tmp_path: Path,
    frozen_contract: RunContract,
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent(),
    )
    other_store = FileRunStore(root=tmp_path / "other-runs")
    other_store.save(frozen_contract)
    other_store.begin(frozen_contract.run_id)
    with pytest.raises(ValueError, match="frozen contract"):
        other_store.finish(result.run)


@pytest.mark.parametrize(
    "kind", ["nested", "existing", "alias", "repository", "commit"]
)
def test_preflight_preserves_created_capture(
    tmp_path: Path, frozen_contract: RunContract, kind: str
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    source = tmp_path / "repository"
    workspace = tmp_path / "work"
    if kind == "nested":
        workspace = source / "nested"
    elif kind == "existing":
        workspace.touch()
    elif kind == "alias":
        alias = tmp_path / "alias"
        alias.symlink_to(source, target_is_directory=True)
        workspace = alias / "nested"
    elif kind == "repository":
        repo = GitRepository(path=tmp_path / "missing")
    else:
        other = tmp_path / "other"
        init_repository(other)
        repo = GitRepository(path=other)
    directory = store.directory(contract.run_id)
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    agent = FakeAgent("clarify")
    with pytest.raises(ValueError):
        execute_run(
            store=store,
            run_id=contract.run_id,
            repository=repo,
            workspace=workspace,
            agent=agent,
        )
    assert agent.calls == []
    assert before == {
        p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()
    }
    assert not (directory / ".execution").exists()
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=GitRepository(path=source),
        workspace=tmp_path / "corrected",
        agent=agent,
    )
    assert result.run.outcome == RunOutcome.NEEDS_CLARIFICATION


def test_default_workspace_uses_custom_runs_root(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    store, repo, contract = capture(tmp_path, frozen_contract)
    result = execute_run(
        store=store, run_id=contract.run_id, repository=repo, agent=FakeAgent()
    )
    assert result.run.outcome == RunOutcome.VERIFIED
    workspace = store.directory(contract.run_id) / "workspace"
    assert result.candidate is not None
    assert git(workspace, "rev-parse", "HEAD") == result.candidate.candidate_sha
    assert (store.directory(contract.run_id) / "evidence.json").is_file()
    assert not (tmp_path / "repository" / ".shipyard").exists()


@pytest.mark.parametrize("kind", ["overlap", "alias", "existing", "file", "permission"])
def test_default_workspace_errors_leave_run_created(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    (store.directory(contract.run_id) / "workspace-layout.json").unlink()
    home = tmp_path / "home"
    if kind == "overlap":
        home = tmp_path / "repository" / "home"
    elif kind == "alias":
        home.symlink_to(tmp_path / "repository", target_is_directory=True)
    monkeypatch.setenv("HOME", str(home))
    workspace = home / ".shipyard" / "workspaces" / str(contract.run_id)
    if kind == "existing":
        workspace.mkdir(parents=True)
    elif kind == "file":
        home.mkdir()
        (home / ".shipyard").write_text("preserve")
    elif kind == "permission":
        original = Path.mkdir

        def denied(
            self: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
        ) -> None:
            if self == workspace.parent:
                raise PermissionError("access denied")
            original(self, mode=mode, parents=parents, exist_ok=exist_ok)

        monkeypatch.setattr(Path, "mkdir", denied)
    agent = FakeAgent()
    with pytest.raises(ValueError) as caught:
        execute_run(store=store, run_id=contract.run_id, repository=repo, agent=agent)
    assert str(workspace) in str(caught.value)
    assert "--workspace" in str(caught.value)
    assert agent.calls == []
    assert store.load_state(contract.run_id).lifecycle.value == "CREATED"
    assert not (store.directory(contract.run_id) / ".execution").exists()
    if kind in {"overlap", "alias"}:
        assert not (tmp_path / "repository" / ".shipyard").exists()
        assert not (tmp_path / "repository" / "home").exists()
    if kind == "file":
        assert (home / ".shipyard").read_text() == "preserve"
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "recovery",
        agent=FakeAgent("clarify"),
    )
    assert result.run.outcome == RunOutcome.NEEDS_CLARIFICATION


@pytest.mark.parametrize("source_ref", ["github:acme/source#42", "file:/task.md"])
def test_candidate_message_uses_frozen_source_and_retains_identities(
    tmp_path: Path, frozen_contract: RunContract, source_ref: str
) -> None:
    from shipyard.domain import Attempt, IntentSnapshot

    intent = IntentSnapshot.create(
        run_id=frozen_contract.run_id,
        source_ref=source_ref,
        markdown="Fixes misleading/prose#99",
    )
    frozen_contract = RunContract.model_validate(
        {**frozen_contract.model_dump(), "intent": intent}
    )
    store, repo, contract = capture(tmp_path, frozen_contract)
    git(
        tmp_path / "repository",
        "remote",
        "add",
        "origin",
        "https://github.com/other/target.git",
    )

    class ConflictingAgent(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            response = super().execute(request)
            if request.stage == AgentStage.BUILD:
                payload = json.loads(response.output)
                payload["plan_update"] = "Closes misleading/agent#100"
                return AgentResponse(returncode=0, output=json.dumps(payload))
            return response

    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=ConflictingAgent(),
    )
    assert result.run.outcome == RunOutcome.VERIFIED
    assert result.candidate is not None
    attempt = Attempt.model_validate_json(
        (store.directory(contract.run_id) / "attempt.json").read_text()
    )
    message = git(
        tmp_path / "repository",
        "show",
        "-s",
        "--format=%B",
        result.candidate.candidate_sha,
    )
    subject = (
        "Shipyard candidate for acme/source#42"
        if source_ref.startswith("github:")
        else "Shipyard candidate"
    )
    assert message == (
        f"{subject}\n\nRun: {contract.run_id}\nAttempt: {attempt.attempt_id}"
    )
    assert result.candidate.attempt_id == attempt.attempt_id
    assert result.run.verification is not None
    assert result.run.verification.candidate == result.candidate


@pytest.mark.parametrize(
    "specification",
    ["# No acceptance declarations", "AC-001: First\nAC-001: Duplicate", "AC-001: "],
    ids=["missing", "duplicate", "empty"],
)
def test_invalid_design_stops_before_plan(
    tmp_path: Path, frozen_contract: RunContract, specification: str
) -> None:
    class InvalidDesign(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            response = super().execute(request)
            if request.stage != AgentStage.DESIGN:
                return response
            data = json.loads(response.output)
            data["artifact"] = specification
            return AgentResponse(returncode=0, output=json.dumps(data))

    store, repo, contract = capture(tmp_path, frozen_contract)
    agent = InvalidDesign()
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
    )
    assert result.run.failure_reason == FailureReason.INVALID_STAGE_OUTPUT
    assert agent.calls == [AgentStage.DESIGN]
    assert result.candidate is None and result.test is None
    assert not (store.directory(contract.run_id) / "design" / "manifest.json").exists()
    assert (store.directory(contract.run_id) / "evidence.json").exists()


@pytest.mark.parametrize("markdown", ["", " \n\t"])
def test_empty_intent_reaches_design_for_clarification(
    tmp_path: Path, frozen_contract: RunContract, markdown: str
) -> None:
    from shipyard.domain import IntentSnapshot

    template = RunContract.model_validate(
        {
            **frozen_contract.model_dump(),
            "intent": IntentSnapshot.create(
                run_id=frozen_contract.run_id,
                source_ref="file:/empty.md",
                markdown=markdown,
            ),
        }
    )
    store, repo, contract = capture(tmp_path, template)

    class Clarify(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            assert request.inputs[0].content == markdown
            response = super().execute(request)
            data = json.loads(response.output)
            data["artifact"] = "What change should be made?"
            return AgentResponse(returncode=0, output=json.dumps(data))

    agent = Clarify("clarify")
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
    )
    assert result.run.outcome == RunOutcome.NEEDS_CLARIFICATION
    assert agent.calls == [AgentStage.DESIGN]
    assert result.contract.intent.markdown == markdown
    assert (store.directory(contract.run_id) / "evidence.json").exists()


def test_test_cannot_verify_hidden_tracked_changes(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(
        tmp_path,
        frozen_contract,
        "git update-index --assume-unchanged shipyard.yaml && echo hidden >> shipyard.yaml",
    )
    agent = FakeAgent()
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
    )
    assert result.test is not None and result.test.collection.passed
    assert "index tracking" in (result.test.workspace_error or "")
    assert result.run.outcome == RunOutcome.TEST_FAILED
    assert AgentStage.REVIEW not in agent.calls
