# Specification: Artifact identity and provenance

This is the acceptance contract for another subset of the PoC domain foundation.

## Acceptance criteria

- **AC-001 — Identity and ownership:** An ArtifactReference requires UUID
  artifact_id and run_id, kind, produced_by, sha256, and size_bytes. Optional
  attempt_id defaults to None. Direct construction requires an explicit artifact
  ID; factory creation generates a fresh UUID4 even for identical content/metadata.
- **AC-002 — Kinds and origins:** ArtifactKind accepts lowercase intent, spec,
  plan, review, report, stage_result, test_evidence, evidence, and log. ArtifactStage
  accepts lowercase intake, design, plan, build, test, review, and package. Enum
  member names are uppercase. Ownership/origin are explicit declarations; no
  filename inference, kind/stage pairing restrictions, or ownership lookup occurs.
- **AC-003 — Content identity:** ArtifactSha256 accepts exactly 64 lowercase
  hexadecimal characters as a strict string, without normalization. size_bytes is
  a strict nonnegative integer; reject booleans, floats, strings, and negatives.
  Direct metadata validation cannot verify unavailable content.
- **AC-004 — In-memory factory:** ArtifactReference.create takes keyword-only
  run_id, kind, produced_by, content bytes, and optional attempt_id. It hashes
  exact bytes with standard-library SHA-256 and records their length, allowing
  empty content. Reject non-bytes content with TypeError. Do not encode text,
  normalize line endings, or retain content in the reference. Validate all
  supplied metadata through normal model construction.
- **AC-005 — Independent versions:** References are immutable artifact-version
  records. Identical content may share a digest across different records, Runs,
  or Attempts. Changed content changes the digest. UUID uniqueness and prevention
  of conflicting stored records are deferred to storage integration.
- **AC-006 — Structured validation:** Reject extra fields, invalid UUIDs,
  unknown enum values, missing required fields, invalid hashes/sizes, assignment,
  and deletion. Metadata errors raise Pydantic validation errors. Valid references
  round-trip through JSON unchanged; serialized data contains no content.
- **AC-007 — Public interface and boundaries:** Export ArtifactKind,
  ArtifactStage, ArtifactSha256, and ArtifactReference through shipyard.domain.
  Add no dependencies, storage fields, filesystem operations, or integration into
  existing models. Existing domain behavior, including rejection of VERIFIED,
  remains unchanged.
- **AC-008 — Documentation:** Record intent, contract, and guidance separately;
  update README with capability, limitations, and the specification link.

## Scope boundaries

Provenance is declared metadata, not proof of execution, authenticity, durability,
or verification. No filesystem paths, provider fields, storage generations,
timestamps, or Candidate references are included. Defer ArtifactStore interfaces,
storage/loading/integrity verification, input lineage, retention, candidate
bundles, and stage-result integration.

Implementation may revise plan.md; acceptance changes must be explicit. Preserve
earlier slice specifications. This slice does not complete PRD Phase 1.
