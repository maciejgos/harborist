# Phase 4 acceptance audit

Date: 2026-10-26.

Result: **Phase 4 complete for the local synchronous PoC; ready for Phase 5.**

Production implementation revision: `dc7eddabc7b1ee86a12ba8abf43b40f13bdcb3b8`.
This audit adds an integration test and documentation without changing production
code. Implementation slices: 027 (`8ca2c52`), 028 (`22ce5c2`), 029 (`dc7edda`).
Every slice has a spec and plan and passed the full validation set before commit.

## PRD mapping

| Phase 4 build item | Implementation | Evidence |
|---|---|---|
| NativeAgent interface | Synchronous execute request/response Protocol; immutable validated context, no resume API | `tests/agents/test_base.py` |
| Codex adapter | Fresh exec with stdin prompt, per-call schema/final-message files, frozen model, explicit sandbox and timeout | `tests/agents/test_codex.py` |
| Fresh invocation semantics | Every execute starts a new ephemeral process; no session identifier is consumed | `test_fresh_exec_uses_final_message_not_stdout`; `test_all_stages_use_independent_codex_processes` |
| DESIGN | Frozen intent and scoped methodology; validated spec.md and stage result | Durable-chain and subprocess integration tests |
| PLAN | Frozen intent/spec and remaining seconds; validated plan.md and stage result | Durable-chain and subprocess integration tests |
| BUILD | Intent/spec/plan, workspace edits, optional separate plan revision, immutable upstream spec | `test_build_cannot_rewrite_spec`; subprocess integration test |
| REVIEW contracts | Exact Attempt/Candidate, successful TEST receipt, clean candidate checkout, read-only sandbox, review.md and existing criterion declarations | Review guards in `test_stages.py`; subprocess integration test; candidate mismatch in `test_base.py` |

Both Phase 4 acceptance statements pass:

1. **Each stage can execute independently from durable upstream artifacts.** The
   application accepts a reloaded frozen contract, Attempt and explicit artifact
   paths. DESIGN produces a spec; a separate invocation consumes that spec for
   PLAN; another consumes spec/plan for BUILD. REVIEW independently consumes the
   spec, supplied TEST evidence and exact candidate. Per-stage request captures
   contain the frozen upstream text and scoped guidance, and validated output is
   persisted with artifact identities and a final completion manifest.
2. **No stage requires agent-session continuity.** The port has no continuation
   operation. The Codex adapter starts one fresh `exec --ephemeral` process with
   explicit inputs on every call and no resume/fork argument. Integration creates
   a new adapter per stage and reloads the frozen contract between invocations.

## Failure and integrity checks

- Nonzero process status cannot become success even with apparently valid output.
- Wrong-stage, malformed, missing-artifact and foreign-candidate final output fail.
- Upstream mutation or deletion prevents a successful capture; BUILD plan changes
  are returned as a separate version instead of rewriting input files.
- Existing output directories are never reused. Partial captures have no success
  manifest. Capture files are created exclusively; the manifest is written last.
- REVIEW rejects failed/foreign TEST receipts and workspace mutation. The system
  Git adapter checks existing HEAD and tracked/untracked/ignored workspace state;
  it never checks out, resets or creates a candidate.
- Provider arguments cannot override workspace/sandbox/session/output semantics.
- Launch errors, missing/invalid UTF-8 final messages and timeouts fail. Timeout
  cleanup targets the fresh process group. Final message reads are size-bounded;
  raw transcripts are discarded and temporary adapter files are removed.

## Validation observed

With the added audit integration test:

- `UV_CACHE_DIR=/tmp/shipyard-uv-cache uv run pytest`: **544 passed**.
- `UV_CACHE_DIR=/tmp/shipyard-uv-cache uv run ruff check .`: **passed**.
- `UV_CACHE_DIR=/tmp/shipyard-uv-cache uv run pyright`: **0 errors, 0 warnings**.

The cache override avoids this environment's read-only default uv cache.
The all-stage integration test crosses the application, Codex adapter, actual
subprocesses, JSON schemas, durable files and a real Git candidate checkout. A
fake executable returns synthetic model responses. The fixture creates/commits
the BUILD change with Git and supplies a synthetic successful TEST receipt; it
is not evidence that Shipyard implements Phase 5 or Phase 6.

Codex invocation flags were checked against installed `codex exec --help` and
[official Codex commands](https://learn.chatgpt.com/docs/developer-commands#codex-exec).
No authenticated live model invocation was run. Provider availability, model
obedience and the remote service's schema compatibility remain unverified live.

## Remaining phase boundaries

- Phase 5: isolated Git workspaces, candidate commit/ref creation and developer
  dirty-checkout isolation. Callers currently supply a prepared workspace.
- Phase 6: trusted mandatory check execution and authoritative evidence. A supplied
  trusted TEST receipt is a caller declaration, not proof that checks ran; this
  phase does not parse evidence contents or reconcile them with check results.
- Phase 7: required-criterion extraction/coverage, evidence validation and VERIFIED
  invariants. Passing agent declarations alone grant no software outcome.
- Phase 8: Run-level lifecycle/event persistence, failure mapping, total budget and
  verification reserve accounting, PACKAGE and terminal-directory immutability.
  Current stage capture is create-only, without atomic multi-file publication or
  power-loss guarantees. Per-call timeout is enforced; remaining budget is supplied
  by the caller. The full AttemptExecutor and CLI run loop remain unimplemented.

The PoC remains trusted-local. Sandboxes, pre/post workspace checks and digest
records do not constitute hostile-code isolation or tamper-proof attestation.
No Phase 4 blocker remains within this scope.
