# Plan: Domain event records

## Interfaces and approach

Prepare intent and spec first. Follow focused red → green → refactor steps:

1. Test RunEvent factory identity, snapshot preservation, and lifecycle matching;
   confirm failure, then implement the five RunEventType values and frozen RunEvent.
2. Test timestamps, Attempt creation, and discriminated JSON round-trips; confirm
   failures, then implement shared aware/UTC timestamp validation, frozen
   AttemptCreatedEvent, and the DomainEvent union.
3. Add focused malformed-data, immutability, and reused-invariant cases. Confirm
   failures before implementing any behavior they expose. Refactor with checks green.
4. Export public interfaces and update README. Keep existing models intact.

RunEvent fields: event_id UUID, occurred_at aware datetime, event_type (one of the
five lifecycle literals), run Run, attempt_id UUID or None. Match event type to
run.lifecycle and derive run_id as an ordinary read-only property.

AttemptCreatedEvent fields: event_id UUID, occurred_at aware datetime, event_type
literal attempt_created, attempt Attempt. Derive run_id and attempt_id properties.

Both create factories accept keyword-only snapshot/context and occurred_at,
generate UUID4, and use validated construction. RunEvent.create also requires
event_type. Direct construction requires the discriminator. Store no duplicate
ownership IDs. Normalize aware timestamps to UTC using the standard library and
Pydantic validation; no clock, I/O, new dependencies, base-class framework, custom
parser, or exception wrapper is needed.

## JSON examples

```json
{
  "event_id": "211662ce-4c86-4e7f-b170-103801e6ebc7",
  "occurred_at": "2026-10-25T12:00:00Z",
  "event_type": "run_started",
  "run": {
    "run_id": "6051cef2-a0bc-4d91-8c77-c4ebc3c51972",
    "lifecycle": "RUNNING",
    "outcome": null,
    "failure_reason": null
  },
  "attempt_id": null
}
```

```json
{
  "event_id": "ee233ab4-d245-4ede-9ac2-c3b9c7e66fab",
  "occurred_at": "2026-10-25T12:00:00Z",
  "event_type": "attempt_created",
  "attempt": {
    "attempt_id": "0d72e28d-42b4-45a5-af93-759c83251137",
    "run_id": "6051cef2-a0bc-4d91-8c77-c4ebc3c51972",
    "start_sha": "0123456789abcdef0123456789abcdef01234567"
  }
}
```

## Verification mapping

- AC-001/002: fresh IDs, preserved snapshots/context, one valid and one mismatched
  lifecycle per event type; no Cartesian products.
- AC-003/004: Attempt ownership/start SHA, Run inconsistency and VERIFIED rejection.
- AC-005: UTC/non-UTC timestamps, instant preservation, naive/missing rejection.
- AC-006/007: both union branches round-trip, discriminators, representative
  malformed nested data, required/extra fields, frozen records and snapshots.
- AC-008: regression suite and source/documentation review.

Run focused tests per step, then `uv run pytest`, `uv run ruff check .`, and
`uv run pyright`. Do not repeat the existing UUID/SHA validation matrices.
