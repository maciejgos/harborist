# Specification: Trusted TEST execution

- AC-001: Execute frozen Run checks on a clean exact candidate belonging to the supplied Attempt and Run. Reject foreign identities, wrong revision and output directories inside the workspace before execution.
- AC-002: Persist full ordered check results, frozen configuration provenance and candidate identity in a create-only manifest written after logs. Repeated capture must not overwrite evidence.
- AC-003: Produce a successful TEST receipt only when every check passes and the workspace remains clean at the same revision. Failures or workspace mutations produce TEST_FAILED, blocking REVIEW through existing routing and stage guards.
- AC-004: Candidate harborist.yaml changes do not alter frozen commands.
