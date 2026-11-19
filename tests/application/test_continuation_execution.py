from pathlib import Path

from harborist.agents.base import AgentRequest, AgentResponse
from harborist.application.execution import execute_run
from harborist.domain import RunContract, RunOutcome
from harborist.domain.continuation import ContinuationRequest
from harborist.domain.stage_result import AgentStage
from harborist.persistence.continuation import prepare_continuation
from tests.application.test_run_execution import FakeAgent, capture
from tests.git_helpers import git


def test_rework_retests_descendant_with_frozen_spec(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent("changes"),
    )
    assert first.attempt is not None
    selected, record = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="rework",
            expected_attempt_id=first.attempt.attempt_id,
            feedback="Fix AC-001",
        ),
    )
    agent = FakeAgent()
    result = execute_run(
        store=selected, run_id=contract.run_id, repository=repo, agent=agent
    )
    assert result.run.outcome == RunOutcome.VERIFIED
    assert agent.calls == [AgentStage.PLAN, AgentStage.BUILD, AgentStage.REVIEW]
    assert result.attempt == record.attempt
    assert result.candidate is not None and first.candidate is not None
    assert result.candidate != first.candidate
    assert (
        git(repo.checkout_root(), "rev-parse", result.candidate.candidate_sha + "^")
        == first.candidate.candidate_sha
    )
    assert result.test is not None and result.test.receipt.candidate == result.candidate
    assert (
        result.run.verification is not None
        and result.run.verification.attempt == result.attempt
    )
    assert result.reused_spec_sha256 == record.spec_digest


class FailingStageAgent(FakeAgent):
    def __init__(self, stage: AgentStage) -> None:
        super().__init__()
        self.failed_stage = stage

    def execute(self, request: AgentRequest) -> AgentResponse:
        if request.stage == self.failed_stage:
            from harborist.agents.base import AgentExecutionError

            self.calls.append(request.stage)
            raise AgentExecutionError("provider unavailable")
        return super().execute(request)


def test_recovery_before_design_starts_fresh(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent("failure"),
    )
    assert first.attempt is not None
    selected, record = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="recover", expected_attempt_id=first.attempt.attempt_id
        ),
    )
    agent = FakeAgent()
    result = execute_run(
        store=selected, run_id=contract.run_id, repository=repo, agent=agent
    )
    assert result.run.outcome == RunOutcome.VERIFIED
    assert agent.calls == list(AgentStage)
    assert record.attempt.start_sha == contract.base_sha
    assert record.spent_seconds > 0
    assert result.timing.remaining_seconds < first.timing.remaining_seconds


def test_recovery_after_review_failure_reverifies_new_candidate(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FailingStageAgent(AgentStage.REVIEW),
    )
    assert first.attempt is not None and first.candidate is not None
    selected, _ = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="recover", expected_attempt_id=first.attempt.attempt_id
        ),
    )
    agent = FakeAgent()
    result = execute_run(
        store=selected, run_id=contract.run_id, repository=repo, agent=agent
    )
    assert result.run.outcome == RunOutcome.VERIFIED
    assert (
        result.attempt is not None
        and result.attempt.start_sha == first.candidate.candidate_sha
    )
    assert result.test is not None and result.test != first.test
    assert agent.calls == [AgentStage.PLAN, AgentStage.BUILD, AgentStage.REVIEW]
