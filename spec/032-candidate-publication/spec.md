# Specification: Candidate publication

- AC-001: An Attempt-bound workspace stages tracked edits/deletions and nonignored new files and creates a candidate commit with explicit Harborist identity. No-change BUILD is valid. Disable commit hooks and signing for harness-created commits.
- AC-002: Require detached HEAD at the frozen start SHA before publication. Reject unmerged state, foreign/attached HEAD and ignored residual files; do not silently discard files. BUILD must leave changes for the harness to commit.
- AC-003: Publish under refs/shipyard/runs/<run-id>/candidate with atomic create-only Git update-ref; never overwrite an existing candidate ref. Return the existing immutable Candidate domain record only after publication and clean exact-SHA validation.
- AC-004: Failures retain inspectable workspace state, never imply verification, and never change developer checkout/index. Real Git tests cover changes, deletions, no-op commits, ref collisions, head drift and ignored residuals.
