"""Acceptance tests for the Run lifecycle contract."""

import json
from collections.abc import Callable
from itertools import product
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shipyard.domain import (
    FailureReason,
    InvalidRunTransition,
    Run,
    RunLifecycle,
    RunOutcome,
)


def run_in_state(lifecycle: RunLifecycle) -> Run:
    return Run(
        run_id=uuid4(),
        lifecycle=lifecycle,
        outcome=(
            RunOutcome.TEST_FAILED if lifecycle == RunLifecycle.COMPLETED else None
        ),
        failure_reason=(
            FailureReason.CONFIGURATION_ERROR
            if lifecycle == RunLifecycle.FAILED
            else None
        ),
    )


OPERATIONS: dict[str, Callable[[Run], Run]] = {
    "start": lambda run: run.start(),
    "complete": lambda run: run.complete(RunOutcome.TEST_FAILED),
    "fail": lambda run: run.fail(FailureReason.CONFIGURATION_ERROR),
    "cancel": lambda run: run.cancel(),
}

ALLOWED_TRANSITIONS = {
    (RunLifecycle.CREATED, "start"): RunLifecycle.RUNNING,
    (RunLifecycle.CREATED, "fail"): RunLifecycle.FAILED,
    (RunLifecycle.CREATED, "cancel"): RunLifecycle.CANCELLED,
    (RunLifecycle.RUNNING, "complete"): RunLifecycle.COMPLETED,
    (RunLifecycle.RUNNING, "fail"): RunLifecycle.FAILED,
    (RunLifecycle.RUNNING, "cancel"): RunLifecycle.CANCELLED,
}


def test_creation() -> None:
    first, second = Run.create(), Run.create()
    assert first.run_id != second.run_id
    assert first.run_id.version == second.run_id.version == 4
    assert first.lifecycle == RunLifecycle.CREATED
    assert first.outcome is None
    assert first.failure_reason is None
    assert Run(run_id=first.run_id) == first


@pytest.mark.parametrize(
    "lifecycle,operation", tuple(product(RunLifecycle, OPERATIONS))
)
def test_transition_matrix(lifecycle: RunLifecycle, operation: str) -> None:
    run = run_in_state(lifecycle)
    before = run.model_dump_json()
    expected = ALLOWED_TRANSITIONS.get((lifecycle, operation))

    if expected is None:
        with pytest.raises(InvalidRunTransition, match="Cannot"):
            OPERATIONS[operation](run)
    else:
        successor = OPERATIONS[operation](run)
        assert successor is not run
        assert successor.run_id == run.run_id
        assert successor.lifecycle == expected
        assert successor.outcome == (
            RunOutcome.TEST_FAILED if expected == RunLifecycle.COMPLETED else None
        )
        assert successor.failure_reason == (
            FailureReason.CONFIGURATION_ERROR
            if expected == RunLifecycle.FAILED
            else None
        )
    assert run.model_dump_json() == before


@pytest.mark.parametrize(
    "lifecycle,outcome,reason",
    [
        pytest.param(RunLifecycle.COMPLETED, None, None, id="completed-needs-outcome"),
        pytest.param(
            RunLifecycle.COMPLETED,
            RunOutcome.TEST_FAILED,
            FailureReason.INTERNAL_ERROR,
            id="completed-forbids-failure-reason",
        ),
        pytest.param(RunLifecycle.FAILED, None, None, id="failed-needs-reason"),
        pytest.param(
            RunLifecycle.FAILED,
            RunOutcome.TEST_FAILED,
            FailureReason.INTERNAL_ERROR,
            id="failed-forbids-outcome",
        ),
        pytest.param(
            RunLifecycle.CREATED,
            RunOutcome.TEST_FAILED,
            None,
            id="created-forbids-outcome",
        ),
        pytest.param(
            RunLifecycle.CREATED,
            None,
            FailureReason.INTERNAL_ERROR,
            id="created-forbids-reason",
        ),
        pytest.param(
            RunLifecycle.RUNNING,
            RunOutcome.TEST_FAILED,
            None,
            id="running-forbids-outcome",
        ),
        pytest.param(
            RunLifecycle.RUNNING,
            None,
            FailureReason.INTERNAL_ERROR,
            id="running-forbids-reason",
        ),
        pytest.param(
            RunLifecycle.CANCELLED,
            RunOutcome.TEST_FAILED,
            None,
            id="cancelled-forbids-outcome",
        ),
        pytest.param(
            RunLifecycle.CANCELLED,
            None,
            FailureReason.INTERNAL_ERROR,
            id="cancelled-forbids-reason",
        ),
        pytest.param(
            RunLifecycle.COMPLETED, RunOutcome.VERIFIED, None, id="verified-reserved"
        ),
    ],
)
def test_inconsistent_state_is_rejected(
    lifecycle: RunLifecycle,
    outcome: RunOutcome | None,
    reason: FailureReason | None,
) -> None:
    with pytest.raises(ValidationError):
        Run(run_id=uuid4(), lifecycle=lifecycle, outcome=outcome, failure_reason=reason)


@pytest.mark.parametrize("lifecycle", RunLifecycle)
def test_valid_state_round_trips(lifecycle: RunLifecycle) -> None:
    run = run_in_state(lifecycle)
    assert Run.model_validate_json(run.model_dump_json()) == run


@pytest.mark.parametrize("outcome", [None, "VERIFIED"])
def test_json_validation_rejects_invalid_completion(outcome: str | None) -> None:
    with pytest.raises(ValidationError):
        Run.model_validate_json(
            json.dumps(
                {
                    "run_id": str(uuid4()),
                    "lifecycle": "COMPLETED",
                    "outcome": outcome,
                }
            )
        )


@pytest.mark.parametrize("outcome", RunOutcome)
def test_completion_outcomes(outcome: RunOutcome) -> None:
    run = Run.create().start()
    if outcome == RunOutcome.VERIFIED:
        with pytest.raises(ValidationError, match="revision-bound verification"):
            run.complete(outcome)
    else:
        completed = run.complete(outcome)
        assert completed.lifecycle == RunLifecycle.COMPLETED
        assert completed.outcome == outcome
        assert completed.failure_reason is None
    assert run.lifecycle == RunLifecycle.RUNNING


@pytest.mark.parametrize("reason", FailureReason)
def test_failure_reasons(reason: FailureReason) -> None:
    failed = Run.create().start().fail(reason)
    assert failed.lifecycle == RunLifecycle.FAILED
    assert failed.failure_reason == reason
    assert failed.outcome is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", uuid4()),
        ("lifecycle", RunLifecycle.CREATED),
        ("outcome", RunOutcome.CHANGES_REQUIRED),
        ("failure_reason", FailureReason.INTERNAL_ERROR),
    ],
)
def test_fields_are_frozen(field: str, value: object) -> None:
    run = Run.create()
    before = run.model_dump_json()
    with pytest.raises(ValidationError, match="frozen"):
        setattr(run, field, value)
    with pytest.raises(ValidationError, match="frozen"):
        delattr(run, field)
    assert run.model_dump_json() == before


@pytest.mark.parametrize(
    "updates",
    [
        {"unexpected": True},
        {"lifecycle": "QUEUED"},
        {"outcome": "SUCCESS"},
        {"failure_reason": "UNKNOWN"},
        {"run_id": "not-a-uuid"},
        {"run_id": None},
        {"lifecycle": None},
    ],
)
def test_invalid_structured_input(updates: dict[str, object]) -> None:
    payload: dict[str, object] = {"run_id": str(uuid4())}
    payload.update(updates)
    with pytest.raises(ValidationError):
        Run.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("payload", ["{", "null", "[]", "{}"])
def test_invalid_json_or_missing_identity(payload: str) -> None:
    with pytest.raises(ValidationError):
        Run.model_validate_json(payload)
