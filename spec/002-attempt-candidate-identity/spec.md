# Specification: Attempt and candidate revision identity

This is the acceptance contract for the second subset of PRD Phase 1.

## Acceptance criteria

- **AC-001 — Attempt identity:** An Attempt has required UUID `attempt_id` and
  owning `run_id`, plus an exact `start_sha`. Factory creation generates a fresh
  UUID4 Attempt ID, even for repeated creation with the same Run and start commit.
  Direct construction requires all identities explicitly.
- **AC-002 — Commit syntax:** Starting and candidate hashes accept exactly 40
  or 64 lowercase hexadecimal characters. Reject abbreviations, refs, whitespace,
  uppercase, non-hexadecimal text, and non-string values without normalization.
- **AC-003 — Candidate ownership:** A Candidate has required `attempt_id` and
  `candidate_sha`. Its identity is that pair. It has no independent UUID and does
  not duplicate the Run ID. An Attempt helper creates a Candidate with its own
  Attempt ID without modifying the Attempt.
- **AC-004 — Immutability:** Every field on Attempt and Candidate rejects
  assignment and deletion. Candidate creation preserves all Attempt fields.
- **AC-005 — Structured validation:** Direct construction, helper methods, and
  validated deserialization enforce the same field constraints. Unknown fields,
  invalid UUIDs, missing required fields, and malformed input are rejected with
  Pydantic validation errors. Valid records round-trip through JSON unchanged.
- **AC-006 — Independent records:** Multiple Attempts may belong to a Run or
  use the same starting SHA. Candidates from separate Attempts may share a SHA
  while retaining distinct identities. A candidate SHA may equal its start SHA.
  Record creation conveys no verification status or shared evidence.
- **AC-007 — Boundaries and compatibility:** Domain code performs no Git,
  filesystem, CLI, or provider operations and adds no dependencies. Existing Run
  behavior remains unchanged, including rejection of VERIFIED. Attempt and
  Candidate are exported alongside a reusable GitCommitSha validation type.
- **AC-008 — Documentation:** Record intent, specification, and plan separately.
  Update README with the new capabilities and a link to this contract. Preserve
  the previous slice's specification.

## Scope boundaries

Syntax validation does not establish repository existence, commit object type,
matching repository object format, or referential integrity. Defer those checks
to adapters and orchestration. Also defer Attempt lifecycle, attachment and
replacement rules, uniqueness enforcement, Git worktrees/refs, persistence,
verification evidence, and rework/recovery execution.

This slice does not complete PRD Phase 1. Implementation may revise plan.md;
acceptance changes must be explicit.
