# Plan: Attempt and candidate revision identity

## Approach and interfaces

1. Prepare the manual intent and acceptance contract before implementation.
2. Add a reusable `GitCommitSha` annotated string type with strict string input
   and a full-match pattern for lowercase 40- or 64-character hexadecimal hashes.
3. Add frozen Pydantic models with forbidden extras: `Candidate(attempt_id,
   candidate_sha)` and `Attempt(attempt_id, run_id, start_sha)`.
4. Add `Attempt.create(run_id, start_sha)` using UUID4 and
   `Attempt.create_candidate(candidate_sha)` returning a separate Candidate with
   its owning Attempt ID. Helpers use validated constructors, not unchecked copies.
5. Export the three additions through `harborist.domain` and update README.

Keep the records separate with no Run back-reference object, embedded candidate,
or infrastructure dependencies. Keep Run unchanged. No new dependencies needed.

## Verification mapping

- AC-001: fresh identities, explicit construction, ownership preservation.
- AC-002: both hash lengths across constructors, helpers, and JSON; invalid hash
  boundaries, text, types, and whitespace, including trailing newlines.
- AC-003/004: helper ownership, unchanged Attempt, all fields frozen.
- AC-005: JSON round-trips, missing/unknown fields, invalid identities/input.
- AC-006: separate Attempt identities for a shared Run/start/candidate commit;
  allow candidate equal to start and standalone Candidate records.
- AC-007/008: existing Run tests plus source and documentation review.

Run focused new domain tests, followed by the full required set:
`uv run pytest`, `uv run ruff check .`, and `uv run pyright`.

## Defaults

Accept both SHA-1 and SHA-256 syntax without normalizing strings. Validate
repository format and ownership existence later. Candidate identity is its
Attempt ID plus SHA; no additional UUID or uniqueness enforcement is introduced.
