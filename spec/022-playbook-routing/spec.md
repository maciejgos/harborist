# Specification: Canonical playbook routing

- AC-001: PlaybookExecution binds a canonical definition, Attempt identity and an
  immutable ordered receipt history. next_stage starts at INTAKE and advances
  only through canonical predecessor completion; no skip/reorder/repeat/restart.
  Construction and JSON reloading enforce the same history rules.
- AC-002: Receipts declare stage/outcome and, where required, Candidate. Success,
  execution failure and cancellation are distinct. NEEDS_CLARIFICATION is valid
  at DESIGN/BUILD, NEEDS_RESCOPING at PLAN/BUILD, TEST_FAILED at TEST and
  CHANGES_REQUIRED at REVIEW. Failure/early exit/cancellation routes to PACKAGE.
- AC-003: BUILD success requires a Candidate belonging to the execution Attempt.
  TEST/REVIEW receipts require exactly that Candidate. A failed mandatory TEST
  routes to PACKAGE and cannot be overridden by later agent/review declarations.
- AC-004: PACKAGE is available after any early exit, outside budget; its receipt
  ends routing even if packaging fails. No stages may follow it. Cancellation
  cannot suppress PACKAGE or cancel PACKAGE itself.
- AC-005: accept returns a newly validated execution and rejects invalid transitions
  with InvalidPlaybookTransition. JSON round-trips preserve identity/history and
  derive the same next stage. No I/O, hooks, subprocess, Run mutation or VERIFIED.

Receipts are trusted orchestrator declarations, not proof of process success,
artifact existence, actual mandatory-check execution, review coverage or budget
compliance. Future executors must establish those facts before submitting receipts.
This slice deliberately does not implement NativeAgent, TEST or workflow persistence.
