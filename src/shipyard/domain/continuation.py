"""Explicit authorization for fresh attempts; never session resumption."""

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.run import FailureReason, Run, RunLifecycle, RunOutcome


class ContinuationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID = Field(default_factory=uuid4)
    action: Literal["rework", "recover"]
    expected_attempt_id: UUID
    feedback: str = Field(default="", max_length=32768)
    additional_seconds: int = Field(default=0, ge=0, strict=True)


def authorize_continuation(
    run: Run,
    previous: Attempt,
    candidate: Candidate | None,
    request: ContinuationRequest,
) -> Attempt:
    """Validate eligibility and lineage without modifying the previous snapshot."""
    if (
        previous.run_id != run.run_id
        or request.expected_attempt_id != previous.attempt_id
    ):
        raise ValueError("Continuation predecessor does not match the latest Attempt")
    if candidate is not None and candidate.attempt_id != previous.attempt_id:
        raise ValueError("Previous candidate belongs to another Attempt")
    if request.action == "rework":
        if run.lifecycle != RunLifecycle.COMPLETED or run.outcome not in {
            RunOutcome.CHANGES_REQUIRED,
            RunOutcome.TEST_FAILED,
        }:
            raise ValueError("Rework requires TEST_FAILED or CHANGES_REQUIRED")
        if candidate is None:
            raise ValueError("Rework requires an exact previous candidate")
    elif run.lifecycle != RunLifecycle.FAILED or run.failure_reason not in {
        FailureReason.EXECUTION_FAILED,
        FailureReason.INVALID_STAGE_OUTPUT,
        FailureReason.CREDENTIAL_UNAVAILABLE,
        FailureReason.CREDENTIAL_REJECTED,
    }:
        raise ValueError("Failure reason is not eligible for explicit recovery")
    return Attempt.create(
        run.run_id, candidate.candidate_sha if candidate else previous.start_sha
    )
