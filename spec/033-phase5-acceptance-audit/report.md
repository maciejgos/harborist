# Phase 5 acceptance audit

Phase 5 is complete for the local synchronous PoC. Implementation revisions:
`15398d8` (workspaces) and `cbc1d65` (candidate publication). This audit also
updates the existing subprocess integration to consume those APIs.

| PRD requirement | Implementation | Evidence |
|---|---|---|
| Base resolution | GitRepository.resolve_base | tests/git/test_repository.py: committed HEAD, refs, tags, detached state, environment isolation |
| Isolated worktree | GitRepository.create_workspace | test_workspace_isolates_all_developer_state; collision/invalid commit test |
| Candidate commit | GitWorkspace.publish_candidate | deletion/new-file candidate and no-op publication tests |
| Candidate ref | Atomic create-only update-ref | test_noop_candidate_and_ref_collision |
| Dirty-checkout isolation | Separate detached checkout; no source staging | test_workspace_isolates_all_developer_state checks staged index, unstaged content, untracked/ignored isolation |
| Developer files unchanged | Worktree creation/publication avoid source checkout | isolation test and independent checkout test |
| TEST independently inspects exact SHA | Candidate ref and SHA usable by separate worktree | test_candidate_is_reachable_and_independently_checkoutable |

`tests/application/test_native_execution.py` now runs DESIGN, PLAN and BUILD via
independent synthetic Codex subprocesses in the Harborist-created workspace, publishes
through Harborist, then performs guarded REVIEW at the candidate SHA. TEST receipts
remain synthetic: no Phase 6 trusted execution or semantic verification is claimed.

Publication rejects HEAD drift, attached HEAD and ignored residue. Hooks/signing
are disabled for harness Git operations. Candidate publication never overwrites a
Run ref, including for another Attempt. Failed publication retains partial state;
retry policy and automatic cleanup are not implemented. Callers must validate
Run/Attempt ownership, require successful BUILD and prevent concurrent writers.
The full CLI workflow, RunStore lifecycle updates and evidence packaging remain
later phases. This is trusted-local state isolation, not agent sandbox security.

Validation: 551 tests passed; Ruff and Pyright passed. No live provider invocation.
