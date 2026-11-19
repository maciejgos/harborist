# Specification: Markdown intake and immutable source snapshot

## Acceptance criteria

- **AC-001 — Snapshot:** IntentSnapshot requires a nonempty strict-string
  source_ref, strict-string markdown, and ArtifactReference artifact. It is frozen,
  forbids extra fields, and derives read-only run_id from its artifact without
  duplicating ownership in serialized output. Valid snapshots round-trip via JSON.
- **AC-002 — Content identity:** The artifact must be INTENT, produced by INTAKE,
  and have no Attempt ownership. Its digest and byte size must match the snapshot's
  UTF-8 content. Validate these relationships on construction/deserialization.
  The create(run_id, source_ref, markdown) factory uses ArtifactReference.create
  for hashing; identical content shares a digest but separate captures have fresh
  artifact IDs.
- **AC-003 — Exact capture:** Preserve Unicode, whitespace, CRLF, optional YAML
  front matter, and a UTF-8 BOM without normalization or metadata extraction.
  Accept empty content; DESIGN assesses whether the request is actionable.
- **AC-004 — File adapter:** read_markdown_intent accepts keyword-only UUID
  run_id and pathlib.Path path, resolves it relative to the current working
  directory with normal symlink behavior, reads its bytes once, and strictly
  decodes UTF-8. Return an IntentSnapshot whose source_ref is file: followed by
  the resolved absolute path. Do not restrict file extensions.
- **AC-005 — Independence and read-only behavior:** After capture, source edits
  and deletion do not affect the snapshot. Retain no live file handle or content
  dependency. Intake performs no writes or Run transitions and leaves input files
  unchanged.
- **AC-006 — Failures:** Missing/unreadable files, directory inputs, and invalid
  UTF-8 raise MarkdownIntakeError, derived from ValueError, with the original
  filesystem/decoding exception as cause. Invalid model metadata remains a
  Pydantic validation error.
- **AC-007 — Interfaces and boundaries:** Export IntentSnapshot through
  harborist.domain and read_markdown_intent/MarkdownIntakeError through
  harborist.intake. Keep domain code free of filesystem operations. Add no
  dependencies or interface hierarchy and preserve existing behavior.
- **AC-008 — Documentation:** Record intent, specification, and plan separately;
  document the callable API and limitations in README and add the intake adapter
  to the architecture code map.

## Completion and exclusions

A caller can capture a local file into validated immutable content/provenance
independent of later source changes. This does not provide durable intent.md,
semantic normalization, YAML parsing, GitHub intake, CLI/file: argument parsing,
Git base resolution, or frozen configuration. It does not complete Phase 2 or the
GitHub-specific frozen-input invariant. Snapshot round-trip stability does not
imply identical serialized output across separate captures with fresh IDs.

Implementation may revise plan.md; acceptance changes must be explicit. Preserve
earlier specifications and historical audit evidence.
