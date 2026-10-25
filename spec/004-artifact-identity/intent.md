# Intent: Artifact identity and provenance

## Source and context

Captured from the owner's request to plan and implement artifact identity and
provenance after the stage-result contracts slice.

Repository HEAD at intake: `e1f0bd0d1ee754cc0508214b4aa59271eaa22bd2`.
This is repository context, not a frozen executable Run contract.

## Requested outcome and decisions

Represent an immutable artifact version through explicit ownership, producing
stage, kind, and exact content identity. The owner selected ownership and origin
metadata without input-artifact lineage, plus a factory that hashes supplied
in-memory bytes without filesystem access.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 7
  (artifact chain), 65 (generic artifact references), 68 (PoC persistence), and
  97 Phase 1 (artifact identities).
- [Architecture](../../ARCHITECTURE.md): infrastructure-independent domain models
  and filesystem-based PoC persistence behind its boundary.

Prepare `intent.md → spec.md → plan.md` manually. These documents do not claim an
executed Shipyard Run or independent agent stages. Preserve earlier specifications.
Storage, lineage, and verification remain future work.
