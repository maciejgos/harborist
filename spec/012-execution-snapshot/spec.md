# Specification: Frozen execution snapshot

- AC-001: Require an ExecutionSnapshot in RunContract. It freezes the canonical
  playbook and ordered skills, agent profile, trusted-local policy and budget.
  Missing execution input is rejected rather than filled with placeholders.
- AC-002: Each methodology asset requires name, explicit version, exact nonblank
  UTF-8 content and matching SHA-256. Only bounded-repository-change is accepted as
  the PoC playbook; skill names are unique. An explicitly empty skill list is valid.
- AC-003: Agent profile requires name/version/provider/model and ordered arguments.
  Provider-specific execution remains outside the domain. All records and nested
  collections are immutable; unknown fields are rejected.
- AC-004: Budget uses strict positive integer seconds for overall execution and
  verification reserve; reserve must be smaller than total. PACKAGE is outside
  the execution budget. These are declarations, not runtime budget enforcement.
- AC-005: Existing ownership/base binding and deterministic JSON serialization
  remain valid. Complete contracts preserve nested execution input on round-trip.

This explicitly extends spec 011's deferred fields. Old minimal contracts are not
silently upgraded to complete contracts. Loading settings, storage, intake and
execution are separate slices. Content capture freezes inputs; Phase 3 owns the
engine and skill composition and Phase 4 owns provider execution.
