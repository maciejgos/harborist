# Intent: Freeze verification configuration from the base commit

## Source and context

Captured from the owner's request to implement the approved verification-config
slice. Repository HEAD: `396fbc3c6f4222938cb6c8c43b8c04ff4e02a99d`.
This is repository context, not a frozen executable Run contract.

The owner selected all configured checks as mandatory and a snapshot containing
validated settings, base SHA, and a digest of the committed source bytes, without
retaining YAML text. Commands remain opaque strings and are not executed.

## Requested outcome

Read shipyard.yaml from one exact base commit and return immutable validated
configuration, unaffected by index/worktree edits or branch advancement. Reject
missing or invalid configuration synchronously without invoking an agent or
changing Run outcomes.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 11
  (verification configuration), 4.9 (frozen contract), and 97 Phases 2 and 6.
- [Architecture](../../ARCHITECTURE.md): system Git behind its adapter, domain
  contracts, and trusted TEST authority.

Prepare intent/spec/plan manually. Defer TEST execution, command/shell semantics,
configuration persistence, agent invocation, and the full frozen Run contract.
Preserve prior specifications and audit history.
