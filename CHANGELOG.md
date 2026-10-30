# Changelog

## Unreleased

- Reject index flags that hide tracked edits before candidate publication and
  exact-revision checks, preventing verification of files absent from the commit.
- Validate READY DESIGN acceptance declarations before PLAN and classify invalid
  specifications as INVALID_STAGE_OUTPUT. Empty requests reach DESIGN unchanged
  so it can request clarification.
- Preserve bounded provider diagnostics when final output is missing, oversized
  or invalid UTF-8.
- Separate CLI registration, command handlers and capture helpers; extract Git
  application transactions behind the existing repository adapter.

## Phase 8 — PACKAGE and evidence (2026-10-27)

- Added synchronous `shipyard run <run-id>` with exclusive one-attempt execution,
  lifecycle journal validation and terminal persistence.
- Added monotonic shared execution budgets, a verification reserve, stage timing
  and shared TEST deadlines with complete collection after exhaustion.
- Added bounded continuously drained subprocess diagnostics, truncation flags and
  optional provider-reported token/actual-charge records; unavailable cost is UNKNOWN.
- Added create-only terminal reports and content-addressed evidence indexes,
  including failed/cancelled/exhausted Runs; PACKAGE stays outside the budget.
- Added real Git/subprocess acceptance coverage, including detached-pipe cleanup
  and cross-contract verification rejection. See the Phase 8 acceptance audit.
  Live-provider/baseline evaluation, recovery and background infrastructure remain out of scope.

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
