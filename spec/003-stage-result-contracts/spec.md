# Specification: Structured native-agent stage-result contracts

This is the acceptance contract for another subset of the PoC domain foundation.

## Acceptance criteria

- **AC-001 — Stage contracts:** DESIGN requires explicit stage `design` and
  status `ready` or `needs_clarification`; PLAN requires `plan` and `ready` or
  `needs_rescoping`; BUILD requires `build` and `ready`, `needs_clarification`, or
  `needs_rescoping`; REVIEW requires `review` and `ready`. Missing fields, unknown
  values, and incompatible combinations are rejected. JSON values are lowercase;
  enum member names are uppercase.
- **AC-002 — REVIEW declaration:** REVIEW requires a Candidate record and at
  least one CriterionResult. Each criterion has an explicit nonempty string ID
  without surrounding whitespace and a status `pass`, `fail`, or `unverified`.
  IDs are unique within a review. Do not normalize them.
- **AC-003 — Derived summary:** REVIEW exposes an immutable ReviewSummary with
  pass_count, fail_count, and unverified_count derived from its criteria. Counts
  are not accepted or serialized as separate REVIEW fields. A ready assessment
  may contain FAIL or UNVERIFIED results and grants no verification authority.
- **AC-004 — Immutable validated data:** Stage results and nested records reject
  extra fields, assignment, and deletion. Criteria are stored as a tuple while
  accepting JSON arrays. Valid results round-trip through JSON; invalid nested
  Candidate or criterion data is rejected through construction/deserialization.
- **AC-005 — Parsing:** A parser accepts a JSON string and expected AgentStage,
  validates a stage-discriminated union, and rejects mismatched stages. Malformed
  JSON, prose-wrapped output, missing/unknown discriminators, invalid fields,
  incompatible statuses, and nested failures raise InvalidStageOutput, derived
  from ValueError. Preserve underlying validation exceptions as causes when
  applicable. Direct model construction raises Pydantic validation errors.
- **AC-006 — Public interfaces:** Export AgentStage, StageStatus,
  CriterionStatus, CriterionResult, ReviewSummary, all four stage-result models,
  StageResult, InvalidStageOutput, and parse_stage_result through harborist.domain.
- **AC-007 — Authority and compatibility:** No agent execution, process checks,
  artifact I/O, workflow transitions, or TEST contracts are added. BUILD contains
  no agent-asserted Candidate. REVIEW's candidate is a declaration pending trusted
  context checks. Existing Run, Attempt, and Candidate behavior remains unchanged,
  including rejection of VERIFIED. Add no dependencies.
- **AC-008 — Documentation:** Keep intent, acceptance, and guidance separate;
  provide JSON examples and acceptance-to-test mapping in plan.md, and describe
  the capability and its boundaries in README.

## Scope boundaries

Process exit success and human-readable artifact existence must be checked
separately before accepting stage execution. Parsing does not extract JSON from
prose, repair output, or infer readiness. Matching the REVIEW declaration to the
actual execution Candidate, checking criterion coverage against frozen spec.md,
and judging evidence sufficiency are later integration work. All-pass reviews
alone cannot produce VERIFIED.

Implementation may revise plan.md. Acceptance changes must be explicit; earlier
slice specifications remain unchanged.
