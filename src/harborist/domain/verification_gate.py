"""Revision-bound positive evidence required to grant VERIFIED."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harborist.domain.attempt import Attempt
from harborist.domain.candidate import Candidate
from harborist.domain.specification import SpecificationReference
from harborist.domain.stage_result import CriterionStatus, ReviewStageResult
from harborist.domain.verification import VerificationConfigSnapshot


class CheckEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: Annotated[str, Field(strict=True, min_length=1)]
    command: Annotated[str, Field(strict=True, min_length=1)]
    passed: Annotated[bool, Field(strict=True)]


class VerificationRecord(BaseModel):
    """Trusted harness attestation, not authority supplied by agent JSON.

    Like other local records, this validates consistency, not authenticity of
    arbitrary operator-authored files. The application checks actual TEST captures.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: UUID
    attempt: Attempt
    candidate: Candidate
    specification: SpecificationReference
    review: ReviewStageResult
    verification: VerificationConfigSnapshot
    checks: Annotated[tuple[CheckEvidence, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_positive_evidence(self) -> Self:
        if (
            self.attempt.run_id != self.run_id
            or self.candidate.attempt_id != self.attempt.attempt_id
            or self.review.candidate != self.candidate
        ):
            raise ValueError("Verification identities must match Run and Candidate")
        if tuple((check.id, check.command) for check in self.checks) != tuple(
            (check.id, check.command) for check in self.verification.config.checks
        ) or not all(check.passed for check in self.checks):
            raise ValueError("Every mandatory check must have passing evidence")
        if {item.criterion_id for item in self.review.criteria} != set(
            self.specification.criterion_ids
        ) or any(item.status != CriterionStatus.PASS for item in self.review.criteria):
            raise ValueError("Every required criterion must PASS")
        return self
