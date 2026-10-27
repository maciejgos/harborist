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
        else:
            artifact = "# Independent review"
            assert request.candidate is not None
            result.update(
                candidate=request.candidate.model_dump(mode="json"),
                criteria=[
                    {
                        "criterion_id": "AC-001",
                        "status": "fail" if self.mode == "changes" else "pass",
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
    "mode,expected",
    [
        ("verified", "VERIFIED"),
        ("clarify", "NEEDS_CLARIFICATION"),
        ("rescope", "NEEDS_RESCOPING"),
        ("changes", "CHANGES_REQUIRED"),
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
    payload = json.loads(result.output)
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
