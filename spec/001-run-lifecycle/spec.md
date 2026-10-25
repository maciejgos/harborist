# Specification: Run lifecycle foundation

This is the acceptance contract for the first subset of PRD Phase 1.

## Acceptance criteria

- **AC-001 — Development baseline:** The project is an installable Python 3.14
  package managed with uv. pytest, Ruff, and strict Pyright check source and tests.
  Dependency resolution is committed in `uv.lock`.
- **AC-002 — Creation and identity:** A new Run has a fresh UUID4 identity,
  CREATED lifecycle, no software outcome, and no failure reason. Its fields cannot
  be reassigned. Transitions preserve identity and leave the original unchanged.
- **AC-003 — Distinct concepts:** Lifecycle is CREATED, RUNNING, COMPLETED,
  FAILED, or CANCELLED. Outcomes are VERIFIED, NEEDS_CLARIFICATION,
  NEEDS_RESCOPING, TEST_FAILED, or CHANGES_REQUIRED. Failure reasons are
  CONFIGURATION_ERROR, EXECUTION_FAILED, INVALID_STAGE_OUTPUT,
  TIME_BUDGET_EXCEEDED, CREDENTIAL_UNAVAILABLE, CREDENTIAL_REJECTED, or
  INTERNAL_ERROR.
- **AC-004 — Transitions:** CREATED may start as RUNNING, fail as FAILED, or
  cancel as CANCELLED. RUNNING may complete as COMPLETED, fail as FAILED, or
  cancel as CANCELLED. Every other transition, including repeated terminal
  operations, is rejected with a domain error derived from ValueError.
- **AC-005 — State consistency:** COMPLETED requires an outcome and forbids a
  failure reason. FAILED requires a failure reason and forbids an outcome.
  CREATED, RUNNING, and CANCELLED forbid both. These rules apply to direct
  construction, validated deserialization, and transitions.
- **AC-006 — Verification reserved:** VERIFIED is defined but rejected on Runs,
  including direct construction and completion, until revision-bound verification
  exists. TEST_FAILED is a valid COMPLETED software outcome, not an execution
  failure.
- **AC-007 — Structured validation:** Valid state round-trips through JSON.
  Unknown fields, unknown enum values, invalid identities, malformed JSON, and
  inconsistent states are rejected with Pydantic validation errors. Transitions
  construct validated instances rather than using unchecked model copying.
- **AC-008 — Boundaries:** Domain code has no CLI, filesystem, Git, GitHub,
  Codex, or other infrastructure dependencies.
- **AC-009 — Documentation:** Intent, acceptance contract, and implementation
  guidance are recorded separately. README documents setup and validation.

## Scope boundaries

Defer Attempts, candidates, verification evidence, events, persistence,
cancellation audit metadata, intake adapters, agents, and orchestration. Omit
QUEUED for synchronous execution. Cancellation here models terminal state only;
it does not terminate processes or persist evidence. This slice does not complete
PRD Phase 1 or implement an executable Shipyard workflow.

Implementation may revise `plan.md`. Acceptance changes must be explicit; BUILD
must not silently rewrite this contract.
