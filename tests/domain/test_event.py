"""Tests for event facts without emission, persistence, or replay."""

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from harborist.domain import (
    Attempt,
    AttemptCreatedEvent,
    DomainEvent,
    FailureReason,
    Run,
    RunEvent,
    RunEventType,
    RunOutcome,
)

WHEN = datetime(2026, 10, 25, 12, tzinfo=UTC)
CREATED = Run.create()
RUNNING = CREATED.start()
ATTEMPT = Attempt.create(CREATED.run_id, "a" * 40)
RUN_FACTS = [
    (RunEventType.RUN_CREATED, CREATED),
    (RunEventType.RUN_STARTED, RUNNING),
    (RunEventType.RUN_COMPLETED, RUNNING.complete(RunOutcome.TEST_FAILED)),
    (RunEventType.RUN_FAILED, RUNNING.fail(FailureReason.EXECUTION_FAILED)),
    (RunEventType.RUN_CANCELLED, RUNNING.cancel()),
]


@pytest.mark.parametrize("event_type,run", RUN_FACTS)
def test_run_event_factory(event_type: RunEventType, run: Run) -> None:
    first = RunEvent.create(event_type=event_type, run=run, occurred_at=WHEN)
    second = RunEvent.create(event_type=event_type, run=run, occurred_at=WHEN)
    assert first.event_id != second.event_id
    assert first.event_id.version == second.event_id.version == 4
    assert first.event_type == event_type
    assert first.run == run
    assert first.run_id == run.run_id
    assert first.attempt_id is None
    assert first.occurred_at == WHEN


@pytest.mark.parametrize("event_type,run", RUN_FACTS)
def test_run_event_rejects_mismatched_snapshot(
    event_type: RunEventType, run: Run
) -> None:
    wrong_run = RUNNING if run == CREATED else CREATED
    with pytest.raises(ValidationError, match="lifecycle"):
        RunEvent.create(event_type=event_type, run=wrong_run, occurred_at=WHEN)


def test_run_event_preserves_attempt_context() -> None:
    attempt_id = uuid4()
    event = RunEvent.create(
        event_type=RunEventType.RUN_STARTED,
        run=RUNNING,
        occurred_at=WHEN,
        attempt_id=attempt_id,
    )
    assert event.attempt_id == attempt_id


def test_timestamp_normalizes_to_utc() -> None:
    local = datetime(2026, 10, 25, 14, tzinfo=timezone(timedelta(hours=2)))
    event = RunEvent.create(
        event_type=RunEventType.RUN_CREATED, run=CREATED, occurred_at=local
    )
    assert event.occurred_at == WHEN
    assert event.occurred_at.tzinfo == UTC


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RunEvent.create(
            event_type=RunEventType.RUN_CREATED,
            run=CREATED,
            occurred_at=datetime(2026, 10, 25, 12),
        )


def test_attempt_creation_event() -> None:
    attempt = Attempt.create(CREATED.run_id, "a" * 40)
    local = datetime(2026, 10, 25, 14, tzinfo=timezone(timedelta(hours=2)))
    event = AttemptCreatedEvent.create(attempt=attempt, occurred_at=local)
    second = AttemptCreatedEvent.create(attempt=attempt, occurred_at=WHEN)
    assert event.event_id != second.event_id
    assert event.event_id.version == second.event_id.version == 4
    assert event.event_type == "attempt_created"
    assert event.occurred_at == WHEN
    assert event.occurred_at.tzinfo == UTC
    assert event.attempt == attempt
    assert event.run_id == attempt.run_id
    assert event.attempt_id == attempt.attempt_id
    assert event.attempt.start_sha == "a" * 40
    assert TypeAdapter(DomainEvent).validate_json(event.model_dump_json()) == event
    assert "run_id" not in event.model_dump()
    assert "attempt_id" not in event.model_dump()


@pytest.mark.parametrize("event_type,run", RUN_FACTS)
def test_run_event_round_trip(event_type: RunEventType, run: Run) -> None:
    event = RunEvent.create(event_type=event_type, run=run, occurred_at=WHEN)
    assert TypeAdapter(DomainEvent).validate_json(event.model_dump_json()) == event
    assert "run_id" not in event.model_dump()


def example_events() -> tuple[RunEvent, AttemptCreatedEvent]:
    return (
        RunEvent.create(
            event_type=RunEventType.RUN_CREATED, run=CREATED, occurred_at=WHEN
        ),
        AttemptCreatedEvent.create(attempt=ATTEMPT, occurred_at=WHEN),
    )


def test_direct_construction_preserves_explicit_identity() -> None:
    event_id = uuid4()
    event = RunEvent(
        event_id=event_id,
        occurred_at=WHEN,
        event_type=RunEventType.RUN_CREATED,
        run=CREATED,
    )
    assert event.event_id == event_id
    attempt_event = AttemptCreatedEvent(
        event_id=event_id,
        occurred_at=WHEN,
        event_type="attempt_created",
        attempt=ATTEMPT,
    )
    assert attempt_event.event_id == event_id


def test_required_event_fields() -> None:
    for event in example_events():
        payload = event.model_dump(mode="json")
        for field in type(event).model_fields:
            if field == "attempt_id":
                continue  # Optional context on RunEvent.
            with pytest.raises(ValidationError, match="Field required"):
                type(event).model_validate(
                    {key: value for key, value in payload.items() if key != field}
                )


def test_attempt_event_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        AttemptCreatedEvent.create(
            attempt=ATTEMPT, occurred_at=WHEN.replace(tzinfo=None)
        )


@pytest.mark.parametrize("event_type", [None, "unknown", "RUN_CREATED"])
def test_union_rejects_unknown_discriminator(event_type: object) -> None:
    payload = {**example_events()[0].model_dump(mode="json"), "event_type": event_type}
    with pytest.raises(ValidationError):
        TypeAdapter(DomainEvent).validate_python(payload)


@pytest.mark.parametrize("raw", ["{", "[]", '{"occurred_at":"2026-10-25T12:00:00Z"}'])
def test_union_rejects_malformed_or_untagged_json(raw: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(DomainEvent).validate_json(raw)


def test_union_validates_event_metadata() -> None:
    run_event, attempt_event = example_events()
    payloads = [
        {**run_event.model_dump(mode="json"), "event_id": "invalid"},
        {**run_event.model_dump(mode="json"), "attempt_id": "invalid"},
        {**attempt_event.model_dump(mode="json"), "occurred_at": "2026-10-25T12:00:00"},
    ]
    for payload in payloads:
        with pytest.raises(ValidationError):
            TypeAdapter(DomainEvent).validate_python(payload)


@pytest.mark.parametrize("outcome", [None, "VERIFIED"])
def test_union_reuses_run_invariants(outcome: str | None) -> None:
    payload = {
        **example_events()[0].model_dump(mode="json"),
        "event_type": "run_completed",
        "run": {
            **CREATED.model_dump(mode="json"),
            "lifecycle": "COMPLETED",
            "outcome": outcome,
        },
    }
    with pytest.raises(ValidationError):
        TypeAdapter(DomainEvent).validate_python(payload)


def test_json_rejects_event_snapshot_mismatch() -> None:
    payload = {
        **example_events()[0].model_dump(mode="json"),
        "event_type": "run_started",
    }
    with pytest.raises(ValidationError, match="lifecycle"):
        TypeAdapter(DomainEvent).validate_json(json.dumps(payload))


def test_union_reuses_attempt_validation() -> None:
    payload = {
        **example_events()[1].model_dump(mode="json"),
        "attempt": {**ATTEMPT.model_dump(mode="json"), "start_sha": "main"},
    }
    with pytest.raises(ValidationError):
        TypeAdapter(DomainEvent).validate_python(payload)


def test_event_records_forbid_extras_and_duplicate_ownership() -> None:
    for event in example_events():
        payload = event.model_dump(mode="json")
        for field in ("extra", "run_id"):
            with pytest.raises(ValidationError, match="extra_forbidden"):
                type(event).model_validate({**payload, field: "unexpected"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AttemptCreatedEvent.model_validate(
            {
                **example_events()[1].model_dump(mode="json"),
                "attempt_id": str(ATTEMPT.attempt_id),
            }
        )


def test_event_fields_and_ownership_properties_are_immutable() -> None:
    run_event, attempt_event = example_events()
    for event in (run_event, attempt_event):
        before = event.model_dump_json()
        for field in (*type(event).model_fields, "run_id"):
            with pytest.raises(ValidationError, match="frozen"):
                setattr(event, field, getattr(event, field))
            with pytest.raises(ValidationError, match="frozen"):
                delattr(event, field)
        assert event.model_dump_json() == before
    snapshots: list[tuple[BaseModel, str]] = [
        (run_event.run, "lifecycle"),
        (attempt_event.attempt, "start_sha"),
    ]
    for snapshot, field in snapshots:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(snapshot, field, "changed")
