# Specification: Phase 1 acceptance audit

## Acceptance criteria

- **AC-001 — Revision scope:** Record baseline Git SHA, UTC audit time, and
  preexisting changes before writing artifacts. Qualify claims if inspected source,
  tests, or configuration differ from HEAD. Identify all inspected evidence sources.
- **AC-002 — Complete traceability:** Assign stable local IDs and findings to
  each of the eight Phase 1 building blocks, five acceptance criteria, and four
  prohibited provider couplings. Cite implementation symbols and runnable pytest
  node selectors for machine-tested claims; use source inspection for boundaries.
- **AC-003 — Honest findings:** Use PASS for directly supported requirements,
  PARTIAL for incomplete behavior/evidence, FAIL for observed contradiction, and
  UNVERIFIED for conclusions unavailable from evidence. Record disposition
  separately; a deferred requirement does not become PASS.
- **AC-004 — Validation baseline:** Run the full required pytest, Ruff, and
  Pyright checks. Record exact commands, exit results, and test totals. Preserve
  failures as findings rather than changing implementation or adding tests.
- **AC-005 — Limits and follow-ups:** Explain what tests prove and omit. Examine
  SHA syntax versus authoritative verification, fresh IDs versus rework/recovery,
  event records versus emission/persistence, domain cancellation versus execution
  cancellation, and the VERIFIED guard versus a complete verification model.
  Every unresolved gap has a concrete completion condition and recommended phase.
- **AC-006 — Separate verdicts:** State domain building-block readiness, full
  Phase 1 acceptance, and readiness to begin Phase 2 independently. Explain later
  phase dependencies without expanding Phase 1 into the entire product or silently
  waiving its stated acceptance criteria.
- **AC-007 — Assessment-only delivery:** Produce intent.md, spec.md, plan.md,
  and report.md under this directory, and a README report link. Leave production
  code, tests, configuration, the PRD, and previous specifications unchanged.

## Boundaries

Passing checks and present model names alone do not prove full acceptance. This
audit does not establish a VERIFIED candidate, authorize scope deferrals, or change
the phase gate. It is a documented assessment of one repository revision, not an
executed Harborist workflow or an independent native-agent REVIEW.

No new tests are required for this documentation-only work. Implementation may
revise plan.md; acceptance changes must be explicit.
