# Plan: Phase 1 acceptance audit

## Procedure

1. Capture HEAD, UTC time, and preexisting changes before creating artifacts.
2. Inspect PRD section 97 Phase 1, ARCHITECTURE.md, all five prior slice
   specifications, every current domain module/test file, and pyproject.toml.
3. Assign P1-B01–B08 to building blocks, P1-A01–A05 to acceptance criteria,
   and P1-D01–D04 to dependency prohibitions. Link findings to source symbols
   and existing pytest selectors. Keep partial/deferred claims separate from PASS.
4. Run the full validation set, recording exact commands and results. The sandbox
   requires the writable cache override `UV_CACHE_DIR=/private/tmp/harborist-uv-cache`;
   use it consistently without changing project configuration.
5. Write report.md with baseline, verdicts, traceability tables, evidence index,
   validation results, limitations, and follow-up completion conditions.
6. Add a README report link. Review artifact links, test selectors, row coverage,
   and diff scope. Ensure source, tests, configuration, and earlier specs still
   match the audited SHA.

## Evidence interpretation

Parametrized function selectors reference all of their collected cases. Cite
test bodies for what is asserted, not just suggestive names. Source inspection
establishes current imports/types and missing integration paths; it is not a
future architecture enforcement test.

Use prior slice scopes as context, not authority to redefine the PRD. Report
domain-only cancellation, syntactic Git IDs, declarations of REVIEW evidence,
and fresh Attempt factories with their integration limitations. Recommend later
phase placement explicitly as a recommendation.

## Completion review

- AC-001: baseline/time/status and final source-diff check.
- AC-002/003: 17 traceability rows, stable IDs, evidence, statuses, and dispositions.
- AC-004: recorded pytest/Ruff/Pyright commands and outcomes.
- AC-005/006: follow-ups and three distinct readiness/acceptance verdicts.
- AC-007: README/new-directory-only changes; no new tests or implementation.

No additional checks are needed after successful validation unless findings or
changes justify them. No audit framework or automatic repairs are introduced.
