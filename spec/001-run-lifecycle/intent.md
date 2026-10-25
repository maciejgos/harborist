# Intent: Run lifecycle foundation

## Source and context

Captured from the owner's request in this conversation to begin the first small
PoC slice, followed by approval of the Python foundation and Run lifecycle plan.
The owner requested specifications in `spec/` and the PRD intake pattern.

Repository HEAD at intake: `d96bb7fafdb7a4615e06fe2e52223238888a262a`.
This is repository context, not a frozen executable Run contract.

## Requested outcome

Establish a working Python package and a small, validated domain model that keeps
Run lifecycle, software outcome, and execution failure separate. Reject invalid
states and transitions, and make cancellation terminal.

The owner selected: reserve the VERIFIED outcome but reject its use until a later
slice implements revision-bound verification.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 6
  (intake/design/plan), 24 (lifecycle/outcomes), 89 (PoC), and 97 Phase 1.
- [Architecture](../../ARCHITECTURE.md): Python 3.14, local synchronous execution,
  Pydantic contracts, and infrastructure-independent domain code.

Apply `intent.md → spec.md → plan.md` manually. These documents do not claim
execution by Shipyard or independent native-agent stage invocations.
