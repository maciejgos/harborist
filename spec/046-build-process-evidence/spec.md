# BUILD process evidence and REVIEW contract

AC-001: BUILD may return a structured process_report containing at most 12 check
records. Each records red/green phase, exact command (up to 2048 characters),
strict integer exit code, and output excerpt (up to 8192 characters). A nonblank
limitations statement (up to 4096 characters) is required. Empty check lists and
unexpected exit codes remain reportable; no workflow success is inferred.

AC-002: The harness saves the validated report as build/build-process.json with
Run/Attempt identity and fixed agent-reported provenance, independent of diagnostic
log truncation. Only BUILD may produce it; legacy responses may omit it.

AC-003: The synchronous executor supplies this optional artifact to REVIEW.
Preflight rejects foreign Run/Attempt identities before invocation, verifies
upstream immutability during invocation, and records the consumed byte digest.
Existing REVIEW callers without a process artifact remain valid.

AC-004: PACKAGE indexes the process artifact and explicitly distinguishes reported
development checks from trusted TEST and independent historical proof. Reported
results never override mandatory TEST or required FAIL/UNVERIFIED assessments.

AC-005: Engineering guidance v2 keeps routine repository TDD policy in operating
guidance, rather than introducing historical-proof product acceptance criteria.
Explicit intent requirements remain required; insufficient independent proof must
be assessed UNVERIFIED. The harness never deletes or weakens existing criteria.

AC-006: Frozen captures are not migrated or rewritten. Packaged defaults and new
example settings adopt engineering v2; canonical playbook v1 remains unchanged.

This slice preserves agent-reported process context, not independently observed
execution receipts. It does not prove actual TDD chronology, execute agent-reported
commands, introduce a new workflow stage, or alter revision-bound verification.
