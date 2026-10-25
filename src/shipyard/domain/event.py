"""Immutable event declarations, separate from execution and event delivery."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from shipyard.domain.attempt import Attempt
from shipyard.domain.run import Run, RunLifecycle


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


type _EventTimestamp = Annotated[AwareDatetime, AfterValidator(_as_utc)]


class RunEventType(StrEnum):
    RUN_CREATED = "run_created"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


_RUN_LIFECYCLES = {
    RunEventType.RUN_CREATED: RunLifecycle.CREATED,
    RunEventType.RUN_STARTED: RunLifecycle.RUNNING,
    RunEventType.RUN_COMPLETED: RunLifecycle.COMPLETED,
    RunEventType.RUN_FAILED: RunLifecycle.FAILED,
    RunEventType.RUN_CANCELLED: RunLifecycle.CANCELLED,
}


class RunEvent(BaseModel):
    """A Run lifecycle declaration without historical or execution authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    occurred_at: _EventTimestamp
    event_type: Literal[
        RunEventType.RUN_CREATED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_COMPLETED,
        RunEventType.RUN_FAILED,
        RunEventType.RUN_CANCELLED,
    ]
    run: Run
    attempt_id: UUID | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.run.lifecycle != _RUN_LIFECYCLES[self.event_type]:
            raise ValueError("Event type must match the Run snapshot lifecycle")
        return self

    @property
    def run_id(self) -> UUID:
        return self.run.run_id

    @classmethod
    def create(
        cls,
        *,
        event_type: RunEventType,
        run: Run,
        occurred_at: datetime,
        attempt_id: UUID | None = None,
    ) -> Self:
        return cls(
            event_id=uuid4(),
            occurred_at=occurred_at,
            event_type=event_type,
            run=run,
            attempt_id=attempt_id,
        )


class AttemptCreatedEvent(BaseModel):
    """An Attempt creation declaration carrying its validated identity snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    occurred_at: _EventTimestamp
    event_type: Literal["attempt_created"]
    attempt: Attempt

    @property
    def run_id(self) -> UUID:
        return self.attempt.run_id

    @property
    def attempt_id(self) -> UUID:
        return self.attempt.attempt_id

    @classmethod
    def create(cls, *, attempt: Attempt, occurred_at: datetime) -> Self:
        return cls(
            event_id=uuid4(),
            occurred_at=occurred_at,
            event_type="attempt_created",
            attempt=attempt,
        )


type DomainEvent = Annotated[
    RunEvent | AttemptCreatedEvent, Field(discriminator="event_type")
]
