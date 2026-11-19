# Intent: Minimal frozen Run contract

## Source and context

Captured from the owner's request to implement the approved minimal frozen Run
contract plan. Repository baseline: `f11d0b762e7fbf461e5e388e152fbc5e6293e407`.
The owner selected a domain-only contract, deferring filesystem persistence.

## Requested outcome

Bind existing captured intent, an exact base SHA, and verification configuration
in an immutable Run-owned record with deterministic serialization. Reject
inconsistent ownership or base provenance without adding execution machinery.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): §§4.9, 6.2,
  and 97 Phase 2.
- [Architecture](../../ARCHITECTURE.md): domain independence and frozen inputs.
- Earlier slices provide intent capture/persistence, Git resolution, and committed
  verification configuration loading.

These documents are manually prepared intake, specification, and implementation
guidance, not artifacts of an executed Harborist workflow. This is a partial
execution contract; full Phase 2 acceptance remains open.
