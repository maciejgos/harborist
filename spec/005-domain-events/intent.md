# Intent: Domain event records

## Source and context

Captured from the owner's request to plan and implement the domain event model
after artifact identities and test cleanup.

Repository HEAD at intake: `83eed2673251fc858a35e90e2b272d0cdfd77b38`.
This records repository context, not a frozen executable Run contract.

## Requested outcome and decisions

Add immutable records for Run lifecycle facts and Attempt creation. The owner
selected records only, validated Run/Attempt snapshots as payloads, and a
cancellation lifecycle fact without full cancellation audit metadata.

Existing domain operations keep their current return types and produce no events.
Later orchestration will create events after successful operations.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 24–25
  (lifecycle/cancellation), 68–69 (persistence/audit), and 97 Phase 1 (events).
- [Architecture](../../ARCHITECTURE.md): infrastructure-independent domain rules
  and filesystem persistence behind its boundary.

Follow the manual `intent.md → spec.md → plan.md` pattern; do not claim an
executed Harborist Run or independent agent stages. Preserve earlier specifications.
Emission, persistence, replay, and full audit behavior remain future work.
