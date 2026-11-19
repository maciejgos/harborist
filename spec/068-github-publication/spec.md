# Phase 12 GitHub publication

- An operator explicitly supplies the full approved candidate SHA and GitHub destination. Harborist validates the latest packaged verification and the Run-owned Git ref before touching the remote.
- Each Run uses a dedicated head branch. New publications require an absent head; updates require the previously published SHA and a Git lease. Updates preserve commits already on the branch.
- A PR describes the request, implementation, base and candidate, TEST and REVIEW, limitations, and local evidence location. GitHub retains merge authority.
- Harborist saves publication preparation and receipts separately from immutable Run evidence. Retrying a partial publication can reconcile an already-pushed head or already-created PR.
