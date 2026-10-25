# Plan: Artifact identity and provenance

## Implementation and interfaces

1. Record manual intake and specification before implementation.
2. Add ArtifactKind and ArtifactStage string-valued enums with lowercase values
   and uppercase names. Keep ArtifactStage separate from the agent-only enum.
3. Add a strict, full-match ArtifactSha256 string type and a frozen
   ArtifactReference Pydantic model with forbidden extra fields. Fields are
   artifact_id/run_id UUIDs, optional attempt_id UUID, kind, produced_by, sha256,
   and strict nonnegative size_bytes.
4. Implement the keyword-only create(run_id, kind, produced_by, content,
   attempt_id=None) factory with UUID4, hashlib.sha256(content).hexdigest(), and
   len(content). Explicitly reject non-bytes with TypeError and use validated
   construction for metadata. Store no content.
5. Export the interfaces and update README. Change no existing model behavior.

Example:

```python
reference = ArtifactReference.create(
    run_id=run.run_id,
    kind=ArtifactKind.INTENT,
    produced_by=ArtifactStage.INTAKE,
    content=b"Requested change\n",
)
```

Direct construction/deserialization validates metadata only. The factory measures
provided bytes, but neither path establishes durability, execution, ownership
existence, or verification. No new dependencies or storage APIs are needed.

## Verification mapping

- AC-001/005: fresh UUID4s, ownership preservation, identical content across
  records/owners, changed content and line endings.
- AC-002: every supported kind/stage and rejected unknown values; no pairing rules.
- AC-003/004: known SHA-256 vectors, empty/ASCII/UTF-8 byte lengths, invalid digest
  syntax/types, strict sizes, rejected non-bytes content, invalid factory metadata.
- AC-006: required/unknown fields, invalid UUIDs, frozen fields, JSON round-trips,
  and no serialized content.
- AC-007/008: existing tests plus source/documentation review and public imports.

Run focused artifact tests, then the full required checks: `uv run pytest`,
`uv run ruff check .`, and `uv run pyright`.
