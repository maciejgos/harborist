"""Monotonic shared execution allowance; PACKAGE never needs admission."""

import math
import time
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.execution import ExecutionBudget


class BudgetExceeded(RuntimeError):
    """No executor allowance remains."""


class Timing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: ArtifactStage | None
    started_at: AwareDatetime
    ended_at: AwareDatetime
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    original_seconds: int = Field(gt=0)
    remaining_seconds: float = Field(ge=0, allow_inf_nan=False)


class BudgetClock:
    def __init__(
        self,
        budget: ExecutionBudget,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.budget = budget
        self._monotonic = monotonic
        self._utcnow = utcnow
        self.started_at = utcnow()
        self._start = monotonic()
        self._last = self._start

    def elapsed(self) -> float:
        now = self._monotonic()
        if not math.isfinite(now) or now < self._last:
            raise ValueError("Monotonic clock must be finite and nondecreasing")
        self._last = now
        return now - self._start

    def allowance(self, stage: ArtifactStage) -> float:
        limit = self.budget.total_seconds
        if stage in (ArtifactStage.DESIGN, ArtifactStage.PLAN, ArtifactStage.BUILD):
            limit -= self.budget.verification_reserve_seconds
        remaining = limit - self.elapsed()
        if remaining < 1:
            raise BudgetExceeded("Execution allowance exhausted")
        return remaining

    def mark(self) -> tuple[datetime, float]:
        return self._utcnow(), self.elapsed()

    def timing(
        self, stage: ArtifactStage | None, mark: tuple[datetime, float] | None = None
    ) -> Timing:
        end = self.elapsed()
        start_time, start = mark or (self.started_at, 0.0)
        return Timing(
            stage=stage,
            started_at=start_time,
            ended_at=self._utcnow(),
            duration_seconds=end - start,
            original_seconds=self.budget.total_seconds,
            remaining_seconds=max(0, self.budget.total_seconds - end),
        )
