# Intent: Attempt and candidate revision identity

## Source and context

Captured from the owner's request to plan and implement the next small PoC slice
after Run lifecycle. The owner approved the plan and selected full SHA-1 and
SHA-256 support, with Attempt and Candidate represented as separate records.

Repository HEAD at intake: `7d1a55e2d98528cd2a6bb1d0f2fe3d0aaedad076`.
This is repository context, not a frozen executable Run contract.

## Requested outcome

Represent one execution within a Run as an immutable Attempt with a starting
commit. Represent its resulting Candidate as an immutable association between
that Attempt and an exact commit. These identities will give later TEST and
REVIEW evidence a revision to reference.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 13
  (candidate identity), 19 (Git model), 21 (Attempt lineage), and 97 Phase 1.
- [Architecture](../../ARCHITECTURE.md): infrastructure-independent domain models
  and exact candidate identity.

Prepare `intent.md → spec.md → plan.md` manually, as in slice 001. These artifacts
do not claim an executed Harborist Run or independent native-agent stages.
This slice models identities only; orchestration, Git operations, and verification
remain future work.
