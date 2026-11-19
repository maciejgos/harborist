# Intent: Markdown intake and immutable source snapshot

## Source and context

Captured from the owner's request to implement the reviewed Markdown intake slice.
Repository HEAD at intake: `6d71fea1b80b9204b8a5ad9e81ae355fa25f6450`.
This is repository context, not a frozen executable Run contract.

The owner confirmed the file-to-snapshot scope: add actual local file reading,
return an immutable in-memory snapshot, and defer writing intent.md. Preserve
optional YAML front matter as text without extracting metadata.

## Requested outcome

Capture exact UTF-8 Markdown content and its source provenance once. Subsequent
source edits or deletion must not change captured intent. Keep filesystem details
in the adapter and validated content identity in the domain.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 6.1–6.2
  (submission/intake), 4.9 (frozen contract), and 97 Phase 2.
- [Phase 1 audit](../006-phase1-acceptance-audit/report.md): intake readiness and
  outstanding execution-level acceptance claims.
- [Architecture](../../ARCHITECTURE.md): local synchronous execution and domain
  independence from filesystem operations.

Prepare intent/spec/plan manually; do not claim an executed Harborist workflow.
This slice captures source text, not normalized semantic intent. Durable storage,
GitHub/CLI intake, and the full frozen Run contract remain future work.
