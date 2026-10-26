# Specification: Minimal frozen Run contract

## Acceptance criteria

- **AC-001 — Composition:** Export RunContract through shipyard.domain. Require
  run_id: UUID, intent: IntentSnapshot, base_sha: GitCommitSha, and
  verification: VerificationConfigSnapshot. Preserve supplied snapshot values
  and identities; generate no IDs, timestamps, or defaults.
- **AC-002 — Binding:** Reject intent.run_id differing from run_id and
  verification.base_sha differing from base_sha. Validated construction and JSON
  loading enforce the same rules with Pydantic validation errors.
- **AC-003 — Immutable record:** Follow frozen Pydantic conventions, forbid extra
  fields, and retain existing nested snapshot validation and immutability.
- **AC-004 — Serialization:** Existing model_dump_json() produces identical
  compact JSON for equivalent validated values, regardless of input mapping key
  order. Existing identities are part of those values. model_validate_json()
  preserves all values on round-trip, including exact Markdown, ordered checks,
  command text, and provenance. No custom serialization format is needed.
- **AC-005 — Domain boundary:** Composition performs no I/O, Git operations,
  normalization, identity generation, lifecycle transitions, or verification
  decisions. Run and existing adapters retain their behavior.
- **AC-006 — Documentation:** Describe the API and composition example in README
  and architecture documentation, explicitly identifying the partial contract and
  remaining execution-semantic fields.

## Completion and exclusions

The caller provides an existing Run ID, captured intent, resolved base SHA, and
loaded verification snapshot. Matching provenance is a consistency check, not
independent proof of committed content. Validated APIs are required; Pydantic's
trusted-data escape hatches are outside the contract.

Defer storage, one-contract-per-Run enforcement, orchestration, CLI/GitHub intake,
playbook/skill versions, agent profile, budget, and policy fields. Do not add
placeholder values or claim an executable Run, full Phase 2 completion, or full
PRD §4.9 compliance. Acceptance changes must be explicit; BUILD may revise plan.md.
