"""Run state and validated, immutable lifecycle transitions."""

from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from harborist.domain.verification_gate import VerificationRecord


class RunLifecycle(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunOutcome(StrEnum):
    VERIFIED = "VERIFIED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NEEDS_RESCOPING = "NEEDS_RESCOPING"
    TEST_FAILED = "TEST_FAILED"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"


class FailureReason(StrEnum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    INVALID_STAGE_OUTPUT = "INVALID_STAGE_OUTPUT"
    TIME_BUDGET_EXCEEDED = "TIME_BUDGET_EXCEEDED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    CREDENTIAL_REJECTED = "CREDENTIAL_REJECTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class InvalidRunTransition(ValueError):
    """An operation is unavailable in the Run's current lifecycle."""


class Run(BaseModel):
    """An immutable Run snapshot; operations return validated successor states.

    VERIFIED requires a validated revision-bound verification record.
    Like other Pydantic contracts, construction and deserialization must use the
    validated APIs, rather than trusted-data escape hatches such as model_construct.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    lifecycle: RunLifecycle = RunLifecycle.CREATED
    outcome: RunOutcome | None = None
    failure_reason: FailureReason | None = None

    verification: VerificationRecord | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.outcome == RunOutcome.VERIFIED:
            if self.verification is None or self.verification.run_id != self.run_id:
                raise ValueError(
                    "VERIFIED requires revision-bound verification for this Run"
                )
        elif self.verification is not None:
            raise ValueError("Only VERIFIED completion may carry verification")
        if self.lifecycle == RunLifecycle.COMPLETED:
            if self.outcome is None or self.failure_reason is not None:
                raise ValueError("COMPLETED requires an outcome and no failure reason")
        elif self.lifecycle == RunLifecycle.FAILED:
            if self.failure_reason is None or self.outcome is not None:
                raise ValueError("FAILED requires a failure reason and no outcome")
        elif self.outcome is not None or self.failure_reason is not None:
            raise ValueError(f"{self.lifecycle} forbids an outcome and failure reason")
        return self

    @classmethod
    def create(cls) -> Self:
        """Create a Run with a fresh UUID4 identity."""
        return cls(run_id=uuid4())

    def start(self) -> Self:
        self._require_source("start", RunLifecycle.CREATED)
        return type(self)(run_id=self.run_id, lifecycle=RunLifecycle.RUNNING)

    def complete(
        self, outcome: RunOutcome, *, verification: VerificationRecord | None = None
    ) -> Self:
        self._require_source("complete", RunLifecycle.RUNNING)
        return type(self)(
            run_id=self.run_id,
            lifecycle=RunLifecycle.COMPLETED,
            outcome=outcome,
            verification=verification,
        )

    def fail(self, reason: FailureReason) -> Self:
        self._require_source("fail", RunLifecycle.CREATED, RunLifecycle.RUNNING)
        return type(self)(
            run_id=self.run_id, lifecycle=RunLifecycle.FAILED, failure_reason=reason
        )

    def cancel(self) -> Self:
        self._require_source("cancel", RunLifecycle.CREATED, RunLifecycle.RUNNING)
        return type(self)(run_id=self.run_id, lifecycle=RunLifecycle.CANCELLED)

    def _require_source(self, operation: str, *allowed: RunLifecycle) -> None:
        if self.lifecycle not in allowed:
            raise InvalidRunTransition(f"Cannot {operation} a {self.lifecycle} Run")
