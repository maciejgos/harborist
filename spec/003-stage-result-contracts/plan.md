# Plan: Structured native-agent stage-result contracts

## Implementation

1. Record the manual intake and acceptance contract before code.
2. Add lowercase string-valued enums for AgentStage, StageStatus, and
   CriterionStatus; add frozen models with forbidden extra fields.
3. Use explicit required stage/status literals for each stage model and a
   stage-discriminated StageResult union. REVIEW reuses Candidate, stores criteria
   as a nonempty tuple, rejects duplicate IDs, and derives a ReviewSummary property.
4. Implement parse_stage_result(raw_json, expected_stage) with a Pydantic
   TypeAdapter. Wrap ValidationError as InvalidStageOutput with exception chaining;
   raise InvalidStageOutput directly for an unexpected stage.
5. Export public interfaces and update README. Keep existing domain models intact.

Criterion IDs are strict nonempty strings; reject surrounding whitespace without
normalizing. ReviewSummary counts are nonnegative strict integers. Its summary
property is not a serialized REVIEW field, avoiding duplicate sources of truth.

## JSON examples

DESIGN:

```json
{"stage": "design", "status": "ready"}
```

PLAN:

```json
{"stage": "plan", "status": "needs_rescoping"}
```

BUILD (Candidate creation/binding occurs later in Harborist-controlled code):

```json
{"stage": "build", "status": "needs_clarification"}
```

REVIEW (ready means the assessment finished, not that the candidate passed):

```json
{
  "stage": "review",
  "status": "ready",
  "candidate": {
    "attempt_id": "a8bf3b18-45b7-4e17-a6ce-38ea4865a18f",
    "candidate_sha": "0123456789abcdef0123456789abcdef01234567"
  },
  "criteria": [
    {"criterion_id": "AC-001", "status": "pass"},
    {"criterion_id": "AC-002", "status": "unverified"}
  ]
}
```

## Verification mapping

- AC-001: all stage/status combinations, missing fields, and unknown values.
- AC-002: empty criteria, duplicate/invalid IDs and statuses, missing nested data.
- AC-003: mixed-status counts, rejected input counts, and omitted serialized summary.
- AC-004: nested candidate validation, frozen fields, tuple storage, JSON round-trips.
- AC-005: parser failures, unexpected stages, exception types and causes, no repair.
- AC-006/007: public imports, existing regression tests, and source review.
- AC-008: documentation review.

Run focused stage-result tests, then `uv run pytest`, `uv run ruff check .`, and
`uv run pyright`. No new dependencies or infrastructure are needed.
