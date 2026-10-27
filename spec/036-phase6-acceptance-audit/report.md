# Phase 6 acceptance audit

Audited implementation: `98a64e8` (runner), `185ec88` (trusted TEST), plus this
commit's real TEST/native-stage integration. No live Codex invocation is claimed.

| Requirement | Implementation / evidence |
|---|---|
| shipyard.yaml and base freezing | Existing verification config loader and frozen RunContract; tests/verification/test_config.py |
| Mandatory executor and complete collection | verification/runner.py; tests/verification/test_runner.py checks failure continuation, output and timeout continuation |
| Every configured check runs | Ordered iteration, including nonzero/timeout failures; complete collection tests |
| Failed mandatory checks prevent REVIEW | TEST_FAILED receipt; existing tests/playbooks/test_routing.py and tests/application/test_stages.py guard routing/REVIEW; trusted execution failure test |
| BUILD config edits cannot change checks | tests/application/test_verification.py commits invalid candidate YAML and proves the original base command executes |
| Exact revision evidence | Candidate cleanliness checked before/after TEST; residue fails closed; manifest binds candidate and frozen configuration |
| Real integration | tests/application/test_native_execution.py uses real Git worktree/publication, subprocess checks and independent synthetic-provider REVIEW |

All 556 tests, Ruff and Pyright pass. The PoC remains local and synchronous.
Full workflow/CLI orchestration, total Run budget accounting, bounded logs and
PACKAGE are future work. Explicit timeout applies independently to every check.
Logs stream to disk without size limits. Checks must leave a clean workspace,
including ignored content; residue is retained, not removed. Configuration and
commands are trusted local input. Caller-supplied receipts are not cryptographic
proof; orchestration must pass the returned receipt and matching manifest.
Captures are create-only, not crash-atomic, and exclusive workspace use is required.
