import pytest

from shipyard.application.review import evaluate_review
from shipyard.application.verification import TestExecution as CapturedTest
from shipyard.domain import Run, RunContract
from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.playbook_execution import StageReceipt, StepOutcome
from shipyard.domain.stage_result import (
    AgentStage,
    CriterionResult,
    CriterionStatus,
    InvalidStageOutput,
    ReviewStageResult,
    StageStatus,
)
from shipyard.verification.runner import CheckCollection, CheckResult


def capture(
    contract: RunContract,
    attempt: Attempt,
    *,
    passed: bool = True,
    candidate: Candidate | None = None,
) -> CapturedTest:
    candidate = candidate or attempt.create_candidate("b" * 40)
    return CapturedTest(
        run_id=contract.run_id,
        attempt_id=attempt.attempt_id,
        verification=contract.verification,
        workspace_error=None,
        collection=CheckCollection(
            checks=tuple(
                CheckResult(
                    id=c.id,
                    command=c.command,
                    returncode=0 if passed else 1,
                    timed_out=False,
                    error=None,
                    stdout_path="stdout",
                    stderr_path="stderr",
                )
                for c in contract.verification.config.checks
            )
        ),
        receipt=StageReceipt(
            stage=ArtifactStage.TEST,
            candidate=candidate,
            outcome=StepOutcome.SUCCEEDED if passed else StepOutcome.TEST_FAILED,
        ),
    )


@pytest.mark.parametrize(
    "status,outcome",
    [
        (CriterionStatus.PASS, "VERIFIED"),
        (CriterionStatus.FAIL, "CHANGES_REQUIRED"),
        (CriterionStatus.UNVERIFIED, "CHANGES_REQUIRED"),
    ],
)
def test_semantic_decision(
    frozen_contract: RunContract, status: CriterionStatus, outcome: str
) -> None:
    attempt = Attempt.create(frozen_contract.run_id, frozen_contract.base_sha)
    test = capture(frozen_contract, attempt)
    candidate = attempt.create_candidate("b" * 40)
    review = ReviewStageResult(
        stage=AgentStage.REVIEW,
        status=StageStatus.READY,
        candidate=candidate,
        criteria=(CriterionResult(criterion_id="AC-001", status=status),),
    )
    decision = evaluate_review(
        contract=frozen_contract,
        attempt=attempt,
        candidate=candidate,
        specification="AC-001: Required",
        review=review,
        test=test,
    )
    assert decision.outcome == outcome
    if decision.verification:
        completed = (
            Run(run_id=frozen_contract.run_id)
            .start()
            .complete(decision.outcome, verification=decision.verification)
        )
        assert Run.model_validate_json(completed.model_dump_json()) == completed
    failed = evaluate_review(
        contract=frozen_contract,
        attempt=attempt,
        candidate=candidate,
        specification="AC-001: Required",
        review=review,
        test=capture(frozen_contract, attempt, passed=False),
    )
    assert failed.outcome == "TEST_FAILED"
    assert failed.verification is None


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "command",
        "receipt",
        "foreign-run",
        "foreign-attempt",
        "configuration",
        "workspace",
    ],
)
def test_inconsistent_test_cannot_grant_verified(
    frozen_contract: RunContract, defect: str
) -> None:
    attempt = Attempt.create(frozen_contract.run_id, frozen_contract.base_sha)
    test = capture(frozen_contract, attempt).model_dump(mode="json")
    if defect == "missing":
        test["collection"]["checks"] = []
    elif defect == "command":
        test["collection"]["checks"][0]["command"] = "true"
    elif defect == "receipt":
        test["collection"]["checks"][0]["returncode"] = 1
    elif defect == "foreign-run":
        test["run_id"] = "00000000-0000-4000-8000-000000000002"
    elif defect == "foreign-attempt":
        test["attempt_id"] = "00000000-0000-4000-8000-000000000002"
    elif defect == "configuration":
        test["verification"]["source_sha256"] = "d" * 64
    else:
        test["workspace_error"] = "dirty"
    candidate = attempt.create_candidate("b" * 40)
    review = ReviewStageResult(
        stage=AgentStage.REVIEW,
        status=StageStatus.READY,
        candidate=candidate,
        criteria=(CriterionResult(criterion_id="AC-001", status=CriterionStatus.PASS),),
    )
    with pytest.raises(ValueError):
        evaluate_review(
            contract=frozen_contract,
            attempt=attempt,
            candidate=candidate,
            specification="AC-001: Required",
            review=review,
            test=CapturedTest.model_validate(test),
        )


def test_incomplete_review_is_invalid_output(frozen_contract: RunContract) -> None:
    attempt = Attempt.create(frozen_contract.run_id, frozen_contract.base_sha)
    candidate = attempt.create_candidate("b" * 40)
    review = ReviewStageResult(
        stage=AgentStage.REVIEW,
        status=StageStatus.READY,
        candidate=candidate,
        criteria=(CriterionResult(criterion_id="AC-001", status=CriterionStatus.PASS),),
    )
    with pytest.raises(InvalidStageOutput):
        evaluate_review(
            contract=frozen_contract,
            attempt=attempt,
            candidate=candidate,
            specification="AC-001: Required\nAC-002: Also required",
            review=review,
            test=capture(frozen_contract, attempt),
        )
