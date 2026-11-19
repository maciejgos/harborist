"""Validate trusted TEST context and assess independent semantic REVIEW."""

from pydantic import BaseModel, ConfigDict

from harborist.application.verification import TestExecution
from harborist.domain.artifact import ArtifactStage
from harborist.domain.attempt import Attempt
from harborist.domain.candidate import Candidate
from harborist.domain.playbook_execution import StageReceipt, StepOutcome
from harborist.domain.run import RunOutcome
from harborist.domain.run_contract import RunContract
from harborist.domain.specification import SpecificationReference
from harborist.domain.stage_result import (
    CriterionStatus,
    InvalidStageOutput,
    ReviewStageResult,
)
from harborist.domain.verification_gate import CheckEvidence, VerificationRecord
from harborist.review.criteria import extract_criteria, validate_coverage


class ReviewDecision(BaseModel):
    """Harness result; callers still own Run persistence and PACKAGE."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: RunOutcome
    specification: SpecificationReference
    verification: VerificationRecord | None
    receipt: StageReceipt


def validate_test_context(
    *,
    contract: RunContract,
    attempt: Attempt,
    candidate: Candidate,
    test: TestExecution,
) -> bool:
    """Reconcile the complete capture, never trusting the receipt in isolation."""
    if (
        attempt.run_id != contract.run_id
        or candidate.attempt_id != attempt.attempt_id
        or test.run_id != contract.run_id
        or test.attempt_id != attempt.attempt_id
        or test.verification != contract.verification
        or test.receipt.stage != ArtifactStage.TEST
        or test.receipt.candidate != candidate
        or tuple((c.id, c.command) for c in test.collection.checks)
        != tuple((c.id, c.command) for c in contract.verification.config.checks)
    ):
        raise ValueError("TEST capture must match frozen Run, Attempt and Candidate")
    passed = test.collection.passed and test.workspace_error is None
    expected = StepOutcome.SUCCEEDED if passed else StepOutcome.TEST_FAILED
    if test.receipt.outcome != expected:
        raise ValueError("TEST receipt contradicts mandatory check evidence")
    return passed


def evaluate_review(
    *,
    contract: RunContract,
    attempt: Attempt,
    candidate: Candidate,
    specification: str,
    review: ReviewStageResult,
    test: TestExecution,
) -> ReviewDecision:
    passed = validate_test_context(
        contract=contract, attempt=attempt, candidate=candidate, test=test
    )
    spec = extract_criteria(specification)
    if review.candidate != candidate:
        raise InvalidStageOutput("REVIEW must assess the exact candidate")
    validate_coverage(spec, review.criteria)
    verification = None
    if not passed:
        outcome = RunOutcome.TEST_FAILED
    elif any(item.status != CriterionStatus.PASS for item in review.criteria):
        outcome = RunOutcome.CHANGES_REQUIRED
    else:
        outcome = RunOutcome.VERIFIED
        verification = VerificationRecord(
            run_id=contract.run_id,
            attempt=attempt,
            candidate=candidate,
            specification=spec,
            review=review,
            verification=contract.verification,
            checks=tuple(
                CheckEvidence(id=c.id, command=c.command, passed=c.passed)
                for c in test.collection.checks
            ),
        )
    return ReviewDecision(
        outcome=outcome,
        specification=spec,
        verification=verification,
        receipt=test.receipt
        if outcome == RunOutcome.TEST_FAILED
        else StageReceipt(
            stage=ArtifactStage.REVIEW,
            candidate=candidate,
            outcome=StepOutcome.SUCCEEDED
            if outcome == RunOutcome.VERIFIED
            else StepOutcome.CHANGES_REQUIRED,
        ),
    )
