from datetime import UTC, datetime

import pytest

from shipyard.application.budget import BudgetClock, BudgetExceeded
from shipyard.domain import ExecutionBudget
from shipyard.domain.artifact import ArtifactStage


def test_shared_budget_reserves_verification_and_records_failed_stage() -> None:
    now = [10.0]
    clock = BudgetClock(
        ExecutionBudget(total_seconds=100, verification_reserve_seconds=20),
        monotonic=lambda: now[0],
        utcnow=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )
    mark = clock.mark()
    now[0] += 80
    with pytest.raises(BudgetExceeded):
        clock.allowance(ArtifactStage.BUILD)
    assert clock.allowance(ArtifactStage.TEST) == 20
    record = clock.timing(ArtifactStage.BUILD, mark)
    assert record.duration_seconds == 80
    assert record.remaining_seconds == 20
    now[0] += 20
    with pytest.raises(BudgetExceeded):
        clock.allowance(ArtifactStage.REVIEW)
    assert clock.timing(None).remaining_seconds == 0


def test_clock_rejects_backward_measurements() -> None:
    values = iter([5.0, 4.0])
    clock = BudgetClock(
        ExecutionBudget(total_seconds=10, verification_reserve_seconds=2),
        monotonic=lambda: next(values),
    )
    with pytest.raises(ValueError, match="nondecreasing"):
        clock.elapsed()
