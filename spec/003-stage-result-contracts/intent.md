# Intent: Structured native-agent stage-result contracts

## Source and context

Captured from the owner's request to plan and implement structured native-agent
stage-result contracts after Run, Attempt, and Candidate identity models.

Repository HEAD at intake: `8e4c5d5df6892da6cc780358bc5d8d6a396d2fd7`.
This records repository context, not an executable frozen Run contract.

## Requested outcome and decisions

Provide validated machine-readable DESIGN, PLAN, BUILD, and REVIEW outputs so
later orchestration need not infer state from prose. The owner selected:

- Defer BUILD's trusted Candidate binding to later Git/orchestration integration.
- Record REVIEW results per criterion and derive summary counts.

Stage contracts do not execute stages, advance Runs, or establish verification.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 6
  (stage behavior), 12–14 (review, candidate identity, and stage contracts), and
  97 Phases 1, 4, and 7.
- [Architecture](../../ARCHITECTURE.md): validated structured results,
  infrastructure-independent domain models, and trusted execution boundaries.

Follow the manually prepared `intent.md → spec.md → plan.md` pattern from earlier
slices. These documents do not claim an executed Shipyard Run or independent
native-agent stage invocations. Existing specifications remain unchanged.
