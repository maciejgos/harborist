# Specification: Filesystem intent persistence

## Acceptance criteria

- **AC-001 — API and paths:** Export FileIntentStore, IntentPersistenceError,
  and IntentAlreadyExistsError through shipyard.persistence. Construction accepts
  keyword-only root Path and performs no I/O. save(snapshot) returns None;
  load(run_id) returns IntentSnapshot. Use <root>/<run-id>/intent.md and intent.json;
  no implicit home directory or additional store hierarchy is introduced.
- **AC-002 — File format:** intent.md stores the exact snapshot UTF-8 bytes,
  including BOM/CRLF. intent.json contains only source_ref and serialized artifact
  metadata, without Markdown content, timestamps, or new identities. Validate
  metadata with a private Pydantic model requiring its fields and forbidding extras.
- **AC-003 — Create-only save:** Revalidate snapshots before filesystem mutation.
  Create missing parent directories and preserve unrelated files in existing Run
  directories. Reject every repeat save if either reserved path exists, including
  incomplete saves and matching content. Preflight paths and create each file
  exclusively; close intent.md before creating intent.json. Preserve existing data.
- **AC-004 — Incomplete state:** On write failure leave any newly created partial
  files for inspection. Do not delete, overwrite, retry, or automatically repair
  them. Incomplete/corrupt state must not load successfully or be overwritten by
  a subsequent save. No atomic multi-file publication is promised.
- **AC-005 — Validated load:** Validate the requested Run UUID before path
  construction. Read/validate metadata, then read intent.md bytes and decode strict
  UTF-8. Reconstruct via IntentSnapshot validation to check digest, size, artifact
  kind, producer, and ownership scope. Require snapshot.run_id to match the requested
  ID. Preserve artifact identity and provenance; never reread source or write files.
- **AC-006 — Errors:** IntentPersistenceError derives from ValueError;
  IntentAlreadyExistsError derives from IntentPersistenceError and denotes save
  conflicts. Wrap filesystem and invalid persisted-data failures with causes and
  operation/path context. Do not include captured content in messages. Invalid
  caller snapshots/Run IDs remain Pydantic validation errors.
- **AC-007 — Compatibility and documentation:** Add no dependencies or changes
  to domain/intake behavior. Document the store API, layout, and limits in README
  and ARCHITECTURE.md. Record specification artifacts separately from implementation.

## Completion and exclusions

Captured intent can be saved and independently loaded with verified content
identity while existing intent is protected from replacement. This does not
establish VERIFIED software outcomes, complete Phase 2, or provide a general
ArtifactStore/RunStore. Defer events, terminal-directory enforcement, recovery,
atomic multi-file publication, power-loss durability, CLI/GitHub integration,
and the full frozen Run contract.

Implementation may revise plan.md; acceptance changes must be explicit.
