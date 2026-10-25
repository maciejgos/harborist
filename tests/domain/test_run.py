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
    tuple(product(RunLifecycle, [None, *RunOutcome], [None, *FailureReason])),
)
def test_state_combinations(
    lifecycle: RunLifecycle,
    outcome: RunOutcome | None,
    reason: FailureReason | None,
) -> None:
    valid = outcome != RunOutcome.VERIFIED and (
        (lifecycle == RunLifecycle.COMPLETED and outcome is not None and reason is None)
        or (lifecycle == RunLifecycle.FAILED and reason is not None and outcome is None)
        or (
            lifecycle
            in (RunLifecycle.CREATED, RunLifecycle.RUNNING, RunLifecycle.CANCELLED)
            and outcome is None
            and reason is None
        )
    )
    run_id = uuid4()
    payload = json.dumps(
        {
            "run_id": str(run_id),
            "lifecycle": lifecycle,
            "outcome": outcome,
            "failure_reason": reason,
        }
    )

    if valid:
        run = Run(
            run_id=run_id, lifecycle=lifecycle, outcome=outcome, failure_reason=reason
        )
        assert Run.model_validate_json(payload) == run
        assert Run.model_validate_json(run.model_dump_json()) == run
    else:
        with pytest.raises(ValidationError):
            Run(
                run_id=run_id,
                lifecycle=lifecycle,
                outcome=outcome,
                failure_reason=reason,
            )
        with pytest.raises(ValidationError):
            Run.model_validate_json(payload)


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
@pytest.mark.parametrize("lifecycle", [RunLifecycle.CREATED, RunLifecycle.RUNNING])
def test_failure_reasons(lifecycle: RunLifecycle, reason: FailureReason) -> None:
    failed = run_in_state(lifecycle).fail(reason)
    assert failed.lifecycle == RunLifecycle.FAILED
    assert failed.failure_reason == reason
    assert failed.outcome is None


@pytest.mark.parametrize("lifecycle", RunLifecycle)
@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", uuid4()),
        ("lifecycle", RunLifecycle.CREATED),
        ("outcome", RunOutcome.CHANGES_REQUIRED),
        ("failure_reason", FailureReason.INTERNAL_ERROR),
    ],
)
def test_fields_are_frozen(lifecycle: RunLifecycle, field: str, value: object) -> None:
    run = run_in_state(lifecycle)
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
        Run.model_validate(payload)
    with pytest.raises(ValidationError):
        Run.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("payload", ["{", "null", "[]", "{}"])
def test_invalid_json_or_missing_identity(payload: str) -> None:
    with pytest.raises(ValidationError):
        Run.model_validate_json(payload)


def test_transition_error_is_value_error() -> None:
    assert issubclass(InvalidRunTransition, ValueError)
