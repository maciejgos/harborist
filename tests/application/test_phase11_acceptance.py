from pathlib import Path

import pytest

from shipyard.agents.base import AgentExecutionError, AgentRequest, AgentResponse
from shipyard.application.budget import BudgetClock
from shipyard.application.execution import execute_run
from shipyard.domain import RunContract, RunOutcome
from shipyard.domain.continuation import ContinuationRequest
from shipyard.domain.stage_result import AgentStage
from shipyard.persistence.continuation import execution_lock, prepare_continuation
from tests.application.test_run_execution import FakeAgent, capture
from tests.git_helpers import git


def test_repeated_rework_preserves_contract_lineage_and_spending(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    root = store.directory(contract.run_id)
    current = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=FakeAgent("changes"),
    )
    original_files = {
        p.relative_to(root): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and not p.is_relative_to(root / "workspace")
    }
    for number, mode in enumerate(["changes", "verified"], 1):
        assert current.attempt is not None and current.candidate is not None
        previous = current
        assert previous.candidate is not None
        selected, record = prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="rework",
                expected_attempt_id=current.attempt.attempt_id,
                additional_seconds=10,
            ),
        )
        current = execute_run(
            store=selected,
            run_id=contract.run_id,
            repository=repo,
            agent=FakeAgent(mode),
        )
        assert selected.selected_number(contract.run_id) == number
        assert current.attempt is not None and current.candidate is not None
        assert current.attempt.start_sha == previous.candidate.candidate_sha
        assert (
            git(
                repo.checkout_root(), "rev-parse", current.candidate.candidate_sha + "^"
            )
            == previous.candidate.candidate_sha
        )
        assert record.granted_seconds == 10 * number
        assert (
            record.spent_seconds
            == previous.timing.original_seconds - previous.timing.remaining_seconds
        )
        assert current.contract == contract
        assert current.reused_spec_sha256 == record.spec_digest
    assert current.run.outcome == RunOutcome.VERIFIED
    assert current.attempt is not None
    with pytest.raises(ValueError, match="Rework requires"):
        prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="rework", expected_attempt_id=current.attempt.attempt_id
            ),
        )
    for path, raw in original_files.items():
        assert (root / path).read_bytes() == raw


class CrashAtPlan(FakeAgent):
    def execute(self, request: AgentRequest) -> AgentResponse:
        if request.stage == AgentStage.PLAN:
            raise SystemExit("simulated worker loss")
        return super().execute(request)


def test_interrupted_rework_preserves_already_frozen_spec(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=FakeAgent("changes"),
    )
    assert first.attempt is not None
    selected, record = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="rework", expected_attempt_id=first.attempt.attempt_id
        ),
    )
    with pytest.raises(SystemExit):
        execute_run(
            store=selected, run_id=contract.run_id, repository=repo, agent=CrashAtPlan()
        )
    request = ContinuationRequest(
        action="recover",
        expected_attempt_id=record.attempt.attempt_id,
        additional_seconds=600,
    )
    recovered, admission = prepare_continuation(
        store=store, run_id=contract.run_id, request=request
    )
    assert admission.spec_digest == record.spec_digest
    agent = FakeAgent()
    result = execute_run(
        store=recovered, run_id=contract.run_id, repository=repo, agent=agent
    )
    assert result.run.outcome == RunOutcome.VERIFIED
    assert AgentStage.DESIGN not in agent.calls
    assert admission.spent_seconds == contract.execution.budget.total_seconds
    assert (
        result.timing.original_seconds == contract.execution.budget.total_seconds + 600
    )


def test_original_worker_loss_reuses_validated_design_and_requires_grant(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    with pytest.raises(SystemExit):
        execute_run(
            store=store,
            run_id=contract.run_id,
            repository=repo,
            workspace=tmp_path / "first",
            agent=CrashAtPlan(),
        )
    from shipyard.domain.attempt import Attempt

    previous = Attempt.model_validate_json(
        (store.directory(contract.run_id) / "attempt.json").read_bytes()
    )
    with pytest.raises(ValueError, match="additional seconds"):
        prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="recover", expected_attempt_id=previous.attempt_id
            ),
        )
    with (
        execution_lock(store, contract.run_id),
        pytest.raises(ValueError, match="active execution"),
    ):
        prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="recover",
                expected_attempt_id=previous.attempt_id,
                additional_seconds=600,
            ),
        )
    selected, record = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="recover",
            expected_attempt_id=previous.attempt_id,
            additional_seconds=600,
        ),
    )
    assert record.spec_digest is not None
    agent = FakeAgent()
    assert (
        execute_run(
            store=selected, run_id=contract.run_id, repository=repo, agent=agent
        ).run.outcome
        == RunOutcome.VERIFIED
    )
    assert agent.calls == [AgentStage.PLAN, AgentStage.BUILD, AgentStage.REVIEW]


class SpendThenFail(FakeAgent):
    def __init__(self, ticks: list[float]) -> None:
        super().__init__()
        self.elapsed_ticks = ticks

    def execute(self, request: AgentRequest) -> AgentResponse:
        self.elapsed_ticks[0] += 1600
        raise AgentExecutionError("provider failed late")


def test_recovery_never_silently_extends_budget(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    ticks = [0.0]
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=SpendThenFail(ticks),
        clock=BudgetClock(contract.execution.budget, monotonic=lambda: ticks[0]),
    )
    assert first.attempt is not None
    with pytest.raises(ValueError, match="remaining budget"):
        prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="recover", expected_attempt_id=first.attempt.attempt_id
            ),
        )
    selected, record = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="recover",
            expected_attempt_id=first.attempt.attempt_id,
            additional_seconds=200,
        ),
    )
    assert record.spent_seconds == 1600 and record.granted_seconds == 200
    result = execute_run(
        store=selected, run_id=contract.run_id, repository=repo, agent=FakeAgent()
    )
    assert result.timing.remaining_seconds <= 400
    assert (
        "Explicit cumulative time grants: 200s"
        in (selected.directory(contract.run_id) / "report.md").read_text()
    )
    assert result.run.outcome == RunOutcome.VERIFIED


def test_incompatible_feedback_requires_new_run(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=FakeAgent("changes"),
    )
    assert first.attempt is not None
    selected, _ = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="rework",
            expected_attempt_id=first.attempt.attempt_id,
            feedback="Replace all acceptance criteria",
        ),
    )
    spec_before = (selected.directory(contract.run_id) / "frozen-spec.md").read_bytes()
    agent = FakeAgent("rescope")
    result = execute_run(
        store=selected, run_id=contract.run_id, repository=repo, agent=agent
    )
    assert result.run.outcome == RunOutcome.NEEDS_RESCOPING
    assert agent.calls == [AgentStage.PLAN]
    assert (
        selected.directory(contract.run_id) / "frozen-spec.md"
    ).read_bytes() == spec_before
    assert result.attempt is not None
    with pytest.raises(ValueError):
        prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="rework", expected_attempt_id=result.attempt.attempt_id
            ),
        )


def test_rework_mandatory_failure_still_blocks_review(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract, "exit 1")
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=FakeAgent(),
    )
    assert first.attempt is not None
    selected, _ = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="rework", expected_attempt_id=first.attempt.attempt_id
        ),
    )
    agent = FakeAgent()
    result = execute_run(
        store=selected, run_id=contract.run_id, repository=repo, agent=agent
    )
    assert result.run.outcome == RunOutcome.TEST_FAILED
    assert result.run.verification is None
    assert agent.calls == [AgentStage.PLAN, AgentStage.BUILD]


def test_damaged_interrupted_design_fails_closed(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from shipyard.domain.attempt import Attempt

    store, repo, contract = capture(tmp_path, frozen_contract)
    with pytest.raises(SystemExit):
        execute_run(
            store=store,
            run_id=contract.run_id,
            repository=repo,
            workspace=tmp_path / "first",
            agent=CrashAtPlan(),
        )
    directory = store.directory(contract.run_id)
    previous = Attempt.model_validate_json((directory / "attempt.json").read_bytes())
    (directory / "design" / "spec.md").write_text("AC-001: changed acceptance")
    with pytest.raises(ValueError, match="digest"):
        prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="recover",
                expected_attempt_id=previous.attempt_id,
                additional_seconds=600,
            ),
        )
    assert store.selected_number(contract.run_id) == 0
