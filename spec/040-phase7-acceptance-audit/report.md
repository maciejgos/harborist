# Phase 7 acceptance audit

Audited slices: `de4d625` (criterion references), `df8cf66` (verification gate),
`a2b7d45` (independent REVIEW), plus this commit's integration and documentation.

| Requirement | Implementation and evidence |
|---|---|
| Criterion extraction/reference | review/criteria.py and domain/specification.py; tests/review/test_criteria.py exercises headings, lists, plain declarations, fences, duplicate/empty declarations, exact UTF-8 digest and coverage |
| PASS/FAIL/UNVERIFIED | Existing structured ReviewStageResult; application/review.py maps complete assessments to VERIFIED or CHANGES_REQUIRED; tests/application/test_review.py |
| review.md | application/stages.py preserves agent Markdown in create-only capture with structured stage result and manifest; real-process acceptance tests verify persisted contents |
| TEST authority | Preflight compares full capture with frozen configuration, ordered IDs/commands, Run/Attempt/candidate and computed result; inconsistent or empty evidence blocks invocation; tests/application/test_review.py and test_stages.py |
| Every required criterion PASS | Exact set coverage plus unique IDs; FAIL/UNVERIFIED never produces verification, missing/foreign IDs produce invalid output without success manifest |
| VERIFIED invariant | domain/verification_gate.py validates positive complete evidence; Run requires matching record for VERIFIED; tests/domain/test_verified.py and existing lifecycle tests exercise construction, transitions, ownership and JSON reload |
| Exact candidate and spec | Pre/post clean-revision guards, upstream byte checks, candidate identity and spec digest, plus TEST capture SHA-256 in REVIEW manifest |
| End-to-end outcome rules | tests/application/test_native_execution.py runs independent synthetic Codex processes, real Git worktrees/commits and real shell TEST for VERIFIED, FAIL, UNVERIFIED and mandatory TEST failure; failure blocks REVIEW, all successful reviews round-trip captures and completed Runs |

Validation: all 594 tests pass; Ruff and Pyright pass.

The explicit PoC spec syntax requires `AC-NNN: text` declarations, optionally as
Markdown list items/headings, or headings with an em dash. All declarations are
required; arbitrary prose is not inferred. Invalid specs are rejected at REVIEW
preflight. Guidance teaches DESIGN this syntax without rewriting earlier frozen
methodology. Earlier captures remain inspectable, but their REVIEW inputs must
satisfy the current explicit contract before execution.

No live authenticated Codex invocation is claimed. Semantic PASS remains an agent
assessment, supported by human-readable review.md; Shipyard validates coverage and
consistency, not the truth of arbitrary prose. Captures/verification records are
trusted-local attestations and do not authenticate maliciously edited files.
Exclusive workspace use is required. Create-only capture is not crash-atomic.
Full Run orchestration, terminal persistence/immutability enforcement, PACKAGE,
reports, total budget accounting and bounded logs remain later work. The existing
CLI still captures intake rather than executing the full workflow.
