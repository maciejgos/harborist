# Intent: Persist captured intent to the local filesystem

## Source and context

Captured from the owner's request to implement create-only intent persistence.
Repository HEAD at intake: `d82b4bbdb4b74f947ba6c9478416aedd7662398a`.
This records repository context, not a frozen executable Run contract.

The owner selected rejection of every repeat save, including identical content,
and detectable incomplete saves: create files exclusively, write metadata last,
and retain partial files for inspection rather than repairing them automatically.

## Requested outcome

Save captured intent as exact intent.md bytes plus snapshot metadata. Load it
without consulting the original issue, validate its content identity and Run
ownership, and protect previously captured intent from accidental replacement.

## Sources and boundaries

- [PRD](../../docs/Product%20Requirements%20Document%20v1.0.md): sections 6.2
  (intake), 68 (filesystem persistence), and 97 Phase 2.
- [Intent snapshot contract](../007-markdown-intake/spec.md): exact content,
  ownership, and artifact consistency.
- [Architecture](../../ARCHITECTURE.md): filesystem persistence behind its boundary.

Prepare intent/spec/plan manually. This is intent persistence only; defer full
RunStore/lifecycle enforcement, events, recovery, and the complete frozen Run
contract. Preserve earlier specifications and audit evidence.
