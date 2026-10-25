# Specification: Domain event records

This is the acceptance contract for the event-record building block of Phase 1.

## Acceptance criteria

- **AC-001 — Identity:** RunEvent and AttemptCreatedEvent require explicit UUID
  event_id and occurred_at on direct construction. Factory creation generates a
  fresh UUID4 event ID and requires an explicit timestamp. Neither factory reads
  the clock.
- **AC-002 — Run facts:** RunEvent requires event_type and a validated Run
  snapshot; optional UUID attempt_id defaults to None. RunEventType values are
  run_created, run_started, run_completed, run_failed, and run_cancelled. They
  require CREATED, RUNNING, COMPLETED, FAILED, and CANCELLED snapshots respectively.
  Reject mismatches. A read-only run_id property derives ownership from the snapshot.
- **AC-003 — Attempt facts:** AttemptCreatedEvent requires event_type
  attempt_created and a validated Attempt snapshot. Its factory supplies the fixed
  type; direct construction/deserialization requires it explicitly. Read-only
  run_id and attempt_id properties derive ownership from the snapshot.
- **AC-004 — Reused invariants:** Run and Attempt snapshots retain existing
  validation, including consistent outcome/failure state and reserved VERIFIED.
  Do not duplicate ownership IDs in serialized records or infer history from a
  snapshot. Optional RunEvent Attempt context is declared, not looked up.
- **AC-005 — Time:** Require timezone-aware timestamps, reject naive datetimes,
  and normalize aware values to UTC while preserving the instant. Missing
  timestamps are rejected; no automatic clock reads occur.
- **AC-006 — Immutable structured records:** Both event models are frozen and
  forbid extra fields. Nested snapshots remain immutable. Valid records round-trip
  through JSON; unknown event types, malformed payloads, invalid IDs, missing
  fields, and inconsistent snapshots are rejected with Pydantic validation errors.
  Derived ownership properties are not serialized.
- **AC-007 — Public interfaces:** Export RunEventType, RunEvent,
  AttemptCreatedEvent, and DomainEvent through shipyard.domain. DomainEvent is a
  Pydantic union discriminated by event_type, usable with TypeAdapter for JSON.
- **AC-008 — Compatibility and documentation:** Preserve Run/Attempt APIs and
  existing behavior. Add no dependencies or infrastructure. Update README with
  capabilities, boundaries, and the specification link; record intent and guidance
  separately from this contract.

## Boundaries

Records describe declarations, not proof of execution or valid event ordering.
They do not emit events, change state, enforce historical sequence or ownership
existence, persist data, replay state, or grant verification. Defer event buses,
handlers, subscribers, sequencing, events.jsonl, full cancellation actor/reason/
stage metadata, and event sourcing. Cancellation here is a terminal lifecycle fact.

Implementation may revise plan.md; acceptance changes must be explicit. This
building block does not replace a separate Phase 1 acceptance audit.
