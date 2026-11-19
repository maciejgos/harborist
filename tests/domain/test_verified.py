from uuid import uuid4

import pytest
from pydantic import ValidationError

from harborist.domain import (
    VerificationCheck,
    VerificationConfig,
    VerificationConfigSnapshot,
)
from harborist.domain.attempt import Attempt
from harborist.domain.run import Run, RunLifecycle, RunOutcome
from harborist.domain.stage_result import (
    AgentStage,
    CriterionResult,
    CriterionStatus,
    ReviewStageResult,
    StageStatus,
)
from harborist.domain.verification_gate import CheckEvidence, VerificationRecord
from harborist.review.criteria import extract_criteria


def record(run: Run) -> VerificationRecord:
    attempt = Attempt.create(run.run_id, "a" * 40)
    candidate = attempt.create_candidate("b" * 40)
    return VerificationRecord(
        run_id=run.run_id,
        attempt=attempt,
        candidate=candidate,
        specification=extract_criteria("AC-001: Required"),
        review=ReviewStageResult(
            stage=AgentStage.REVIEW,
            status=StageStatus.READY,
            candidate=candidate,
            criteria=(
                CriterionResult(criterion_id="AC-001", status=CriterionStatus.PASS),
            ),
        ),
        verification=VerificationConfigSnapshot(
            base_sha="a" * 40,
            source_sha256="c" * 64,
            config=VerificationConfig(
                version=1, checks=(VerificationCheck(id="test", command="true"),)
            ),
        ),
        checks=(CheckEvidence(id="test", command="true", passed=True),),
    )


def test_verified_completion_requires_valid_record_and_round_trips() -> None:
    run = Run.create().start()
    proof = record(run)
    completed = run.complete(RunOutcome.VERIFIED, verification=proof)
    assert completed.verification == proof
    assert Run.model_validate_json(completed.model_dump_json()) == completed
    assert completed.verification is not None
    assert completed.verification.candidate.candidate_sha == "b" * 40


@pytest.mark.parametrize(
    "mutation",
    [
        "failed-check",
        "missing-check",
        "unknown-check",
        "duplicate-check",
        "fail",
        "unverified",
        "missing-criterion",
        "unknown-criterion",
        "foreign-candidate",
    ],
)
def test_invalid_evidence_cannot_be_reloaded(mutation: str) -> None:
    payload = record(Run.create()).model_dump(mode="json")
    if mutation == "failed-check":
        payload["checks"][0]["passed"] = False
    elif mutation == "missing-check":
        payload["checks"] = []
    elif mutation == "unknown-check":
        payload["checks"][0]["id"] = "foreign"
    elif mutation == "duplicate-check":
        payload["checks"] *= 2
    elif mutation in ("fail", "unverified"):
        payload["review"]["criteria"][0]["status"] = mutation
    elif mutation == "missing-criterion":
        payload["review"]["criteria"] = []
    elif mutation == "unknown-criterion":
        payload["review"]["criteria"][0]["criterion_id"] = "AC-999"
    else:
        payload["review"]["candidate"]["candidate_sha"] = "c" * 40
    with pytest.raises(ValidationError):
        VerificationRecord.model_validate(payload)


def test_record_cannot_transfer_to_another_run_or_nonverified_state() -> None:
    run = Run.create().start()
    proof = record(run)
    with pytest.raises(ValidationError):
        Run(
            run_id=uuid4(),
            lifecycle=RunLifecycle.COMPLETED,
            outcome=RunOutcome.VERIFIED,
            verification=proof,
        )
    with pytest.raises(ValidationError):
        run.complete(RunOutcome.CHANGES_REQUIRED, verification=proof)
    with pytest.raises(ValidationError):
        Run(run_id=run.run_id, verification=proof)
