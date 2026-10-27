# Phase 8 acceptance audit

Phase 8 implements PACKAGE and evidence for the local synchronous PoC. One
`shipyard run <run-id>` now connects the previously independent stage boundaries,
including failure mapping, shared deadlines and terminal lifecycle persistence.
No background control plane, recovery, database or publication workflow was added.

## Acceptance mapping

| Requirement | Implementation | Verification |
|---|---|---|
| Every terminal outcome produces a report | `execute_run` maps validated early exits, failed TEST, failed REVIEW, invalid output, execution errors and cancellation; `package_run` writes report/evidence | `tests/application/test_run_execution.py::test_terminal_results_always_package`, `test_failed_test_blocks_review_and_packages`, `test_unexpected_agent_error_still_packages`; standalone terminal cases in `test_package.py` |
| PACKAGE survives exhausted budget | No budget admission in `package_run`; independent PACKAGE timing preserves remaining execution allowance | `test_exhaustion_packages_without_another_executor` proves report/evidence at zero remaining budget |
| Exact candidate and frozen provenance | Existing Git/TEST/REVIEW boundaries composed through canonical receipts; PACKAGE reconciles VERIFIED against DESIGN/TEST/REVIEW | VERIFIED integration case, existing native execution/review suites; cross-contract verification regression |
| Evidence index | Relative paths, byte lengths and SHA-256 of regular files, report included; evidence index written last | `test_package_terminal_outcomes_without_admission`, symlink and repeat-publication rejection |
| Bounded execution logs | Shared nonblocking pipe drain retains 64 KiB per stream, explicit truncation flags, process-group termination; failed native calls retain diagnostics | `test_logs_are_bounded_and_truncation_is_explicit`, `test_failed_native_process_retains_bounded_diagnostics`, `test_detached_descendant_cannot_keep_capture_open` |
| Complete TEST collection within one allowance | Shared deadline limits sequential checks; unstarted checks receive timed-out records and empty logs | `test_total_deadline_records_unstarted_checks`, existing failed-check collection tests |
| Usage and cost | Optional normalized input/output/cached tokens; at most 4096 bytes of provider metadata; actual charge requires currency; unavailable charge UNKNOWN | `tests/agents/test_usage.py`, report UNKNOWN assertions |
| Time accounting | Injected monotonic clock, UTC start/end, original/remaining budget, measured Run/stage durations; DESIGN/PLAN/BUILD reserve verification time | `tests/application/test_budget.py`, exhaustion integration case, per-stage timing evidence |
| Durable terminal lifecycle | Exclusive execution admission, append-only lifecycle events and validated snapshot reload; terminal reruns rejected | terminal integration byte-for-byte immutability checks, journal tampering rejection, CLI integration |

## Slice contracts and commits

1. [041 execution budget](../041-execution-budget/spec.md): `de8cfd7`.
2. [042 bounded logs and usage](../042-bounded-logs-usage/spec.md): `762a33d`.
3. [043 PACKAGE evidence](../043-package-evidence/spec.md): `15993e0`.
4. [044 synchronous execution](../044-run-execution/spec.md): `d039ac5`.
5. [045 acceptance audit](spec.md): this audit, documentation and acceptance-driven
   boundary refinements form the final slice.

Each behavior slice started with focused tests and was validated with the full
pytest, Ruff and Pyright set before its commit. Tests were first observed failing
for the absent API or missing behavior, then passing after implementation. The
budget slice used an isolated implementation file during the red check. uv's
cache was redirected to `/tmp/shipyard-uv-cache` because the default cache is
outside the permitted write locations; this changes no application behavior.

The audit reproduced and corrected two integration defects: verification from a
different frozen contract could enter terminal persistence under the same Run ID,
and a detached descendant retaining stdout/stderr could delay capture beyond the
executor's lifetime. Regression tests failed before both corrections. The latter
fix closes remaining inherited pipes without waiting for detached descendants;
process isolation remains best-effort, not a security boundary.

Final validation: **623 tests passed**, Ruff clean, Pyright clean. Tests use real
Git and subprocess checks with synthetic native agents. The existing synthetic
Codex subprocess suite continues to exercise fresh invocation and exact-candidate
verification independently of the new application orchestration suite.

## Public operation and limits

- Capture with `shipyard intake`, then execute with `shipyard run <run-id> --repo
  <repository>`. Report/evidence paths and terminal state are returned as JSON.
- The current Codex adapter does not extract provider token/billing counters.
  Their values stay unknown; no cost estimate is presented as an actual charge.
- PACKAGE records its own timing outside execution admission. Its timing ends
  after indexing the report and before serializing the final evidence index.
- Lifecycle journal/snapshot writes are not a multi-file transaction. Crashes
  between them fail closed on reload. Partial execution/PACKAGE blocks retries.
- Disk or permission failure can prevent report creation; errors are surfaced
  after terminal state persistence where possible. The harness cannot guarantee
  durable output on an unavailable filesystem.
- Terminal immutability is enforced through the store/executor interfaces, not
  OS permissions. Concurrent or malicious local writers remain unsupported.
- Ctrl-C cancellation is supported; hard process kills, SIGTERM recovery,
  automatic workspace cleanup and re-admission are not implemented.
- Mandatory checks must leave the candidate workspace clean, including ignored
  files. All checks are collected, but commands are not started after the shared
  TEST deadline. Git subprocesses retain existing synchronous behavior without
  new per-command deadlines; the next stage admission checks elapsed time.
- No authenticated live Codex smoke test, direct-Codex baseline evaluation or
  claim about semantic reviewer quality is included. Phase 9 evaluation remains.
