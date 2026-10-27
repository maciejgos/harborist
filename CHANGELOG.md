# Changelog

## Phase 7 — REVIEW and VERIFIED (2026-10-27)

- Added explicit required criterion extraction and exact-content spec references.
- REVIEW validates complete trusted TEST captures and exact criterion coverage,
  persisting review.md and a harness decision bound to the candidate.
- VERIFIED Run completion requires validated all-PASS review and mandatory checks,
  including on JSON reload. FAIL/UNVERIFIED yields CHANGES_REQUIRED.
- Added real Git/subprocess acceptance coverage and the Phase 7 audit. Full workflow
  orchestration, PACKAGE and Run budget accounting remain future work.

## Phase 6 — Deterministic TEST (2026-10-27)

- Added sequential mandatory checks with complete collection, file output and
  per-command timeouts with process-group termination.
- Added create-only exact-candidate TEST captures consuming frozen configuration;
  check failures and workspace mutations produce TEST_FAILED receipts.
- Integrated real trusted TEST into the native-stage/Git acceptance chain.
  Full CLI orchestration, total budget accounting and PACKAGE remain later work.

## Phase 5 — Git workspaces and candidates (2026-10-26)

- Added detached Attempt workspaces at exact base commits while preserving dirty
  developer files and index.
- Added Shipyard candidate commits and atomic create-only Run refs, independently
  checkoutable by exact SHA, with hook/signing suppression and clean-state guards.
- Added real Git acceptance tests, native subprocess integration and Phase 5 audit.
  Trusted TEST, full workflow orchestration and cleanup remain later work.

## Phase 4 — Native-agent stage execution (2026-10-26)

- Added a provider-neutral synchronous NativeAgent port, stage-specific structured
  output schemas and validated artifact/candidate contracts.
- Added fresh Codex CLI invocations with explicit model/workspace/sandbox,
  restricted profile arguments, timeout process-group cleanup and bounded output.
- Added independent durable DESIGN/PLAN/BUILD/REVIEW execution with frozen guidance,
  create-only captures, upstream mutation checks and exact-candidate REVIEW guards.
- Added synthetic subprocess/real-Git acceptance coverage and a Phase 4 audit.
  Full workflow execution, Git isolation/candidate creation, trusted TEST and
  semantic verification remain later phases. Live provider calls are untested.
