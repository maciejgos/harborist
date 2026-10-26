# Intent: Git base SHA resolution

## Source and context

Captured from the owner's request to implement the approved Git resolution slice.
Repository HEAD at intake: `cfa085bcf338ab4daf9de0990b2c9745385ed642`.
This is repository context, not a frozen executable Run contract.

The owner selected native Git commit-ish syntax and isolation from inherited
repository-location/object-store variables. Preserve normal Git configuration.

## Requested outcome

Resolve committed HEAD or an explicit commit-ish in a supplied repository to one
validated full commit SHA, without changing developer state. Returned hashes remain
ordinary immutable values; later Run creation will resolve once and persist them.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 19.1–19.2
  (base selection and dirty state) and 97 Phases 2 and 5.
- [Architecture](../../ARCHITECTURE.md): system Git behind an adapter, subprocess
  execution, and provider-independent domain types.

Prepare intent/spec/plan manually. Defer workspaces, candidates, CLI flags,
GitHub access, configuration freezing, and Run contract integration. Preserve
earlier specifications and audit history.
