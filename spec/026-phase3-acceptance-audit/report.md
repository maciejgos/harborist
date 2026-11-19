# Phase 3 acceptance audit

Date: 2026-10-26.

Result: **Phase 3 complete for the synchronous local PoC; ready for Phase 4.**

Audited implementation revision:
`9b3d58c20a8880be0a372df499cfb7adac40f0e5`, with a clean working tree.
The audit/documentation commit changes no executable code. Work is split across
specifications and commits 019–025, followed by this audit slice.

## PRD Phase 3 mapping

| Build item | Implementation | Acceptance evidence |
|---|---|---|
| Canonical playbook definition | Frozen PlaybookDefinition and canonical_playbook factory; packaged v1 Markdown | `test_canonical_definition_has_fixed_authority_and_dependencies`; defaults compilation test |
| Stages | Exactly INTAKE, DESIGN, PLAN, BUILD, TEST, REVIEW, PACKAGE | Full successful receipt history test; weakened-workflow rejection tests |
| Dependencies | Fixed immediate predecessors; immutable validated receipt history | `test_rejects_weakened_workflow`; `test_cannot_skip_test_or_erase_it_in_rehydrated_history` |
| Executor types | Harborist INTAKE/PACKAGE, fresh native agents for DESIGN/PLAN/BUILD/REVIEW, trusted TEST; read-only REVIEW and unbudgeted PACKAGE | Canonical authority test; engine gating and Candidate drift tests |
| Skill composition | Strict skill front matter and ordered stage filtering into immutable guidance sections | `test_stage_composition_preserves_scope_order_and_exact_bodies`; trusted-stage rejection tests |
| Version identities | Header/asset name-version matching and identity including kind/name/version/exact source SHA-256 | `test_parse_preserves_content_and_binds_version_identity`; invalid metadata/version tests |

Both Phase 3 acceptance statements pass:

1. **The playbook cannot skip mandatory stages.** Definition validation rejects
   omitted, duplicated, reordered or weakened stages/dependencies/authority.
   Successful routing accepts only the next canonical stage. Skipping TEST or
   deleting it from a reloaded history fails. BUILD establishes a Candidate for
   the current Attempt; TEST and REVIEW retain that exact Candidate. Failed TEST
   routes to PACKAGE, blocks REVIEW and cannot be replaced by a later success.
   Early failure, cancellation and clarification/rescoping intentionally stop
   software work and retain PACKAGE; those are terminal paths, not successful
   bypasses of required stages. PACKAGE ends routing even if packaging fails.
2. **Skills cannot independently alter workflow topology.** Skill metadata has
   identity, version, description and native-agent scope only. Unknown topology,
   dependency, executor and hook fields fail. Skill text is opaque guidance in
   separate sections and cannot modify the immutable playbook. The test with
   prose requesting 'Skip TEST' confirms canonical TEST authority/dependencies
   remain unchanged. This establishes control-plane separation; it does not claim
   that a future model will obey arbitrary prompt text without adapter safeguards.

## Frozen inputs and adoption

- New Run creation compiles all frozen methodology before Git/source/storage I/O.
  Regression tests first demonstrated that legacy plain Markdown, weakened TEST
  authority and skill hooks were incorrectly accepted; the gate rejects all three
  without publishing a Run directory.
- Phase 2 snapshots remain loadable and inspectable without silent rewriting.
  Plain legacy documents cannot compile until explicitly migrated into a new
  correctly versioned capture; existing captures are never overwritten.
- Settings loading still captures bytes. Application orchestration owns compilation.
  Compilers and guidance composition consult no live files, refs or settings.
- Packaged version 1 playbook and engineering skill match standalone examples.
  Resource loading works independently of cwd. Agent profile/model choice remains
  explicit; no provider-specific launch logic is introduced.

## Validation observed

At the audited clean implementation revision:

- `uv run pytest -q`: **528 passed**.
- `uv run ruff check .`: **passed**.
- `uv run pyright`: **0 errors, 0 warnings**.
- Installed `harborist methodology --help`: passed.
- Offline wheel build: passed. Both Markdown resources were verified inside the
  wheel. A fresh Python process imported Harborist directly from the wheel and
  successfully loaded/parsed both bundled methodology assets.

A writable UV_CACHE_DIR override was used for this local environment.

Installed CLI and pure-engine smoke check against the audited committed SHA:

1. Copy standalone example issue/settings/playbook/skill to a temporary directory.
2. Create a Run through installed `harborist intake`, targeting this repository.
3. Confirm the frozen base equals the audited SHA; delete all copied input files.
4. Preview saved methodology and REVIEW guidance through installed CLI commands.
   Confirm seven stages, matching playbook digest and engineering skill scope.
5. Confirm saved contract bytes are unchanged.
6. Compile the saved snapshot and exercise pure routing with explicit synthetic
   trusted-harness receipts: progress to BUILD, record TEST_FAILED, confirm REVIEW
   rejection, then accept PACKAGE and confirm routing ends.

All six steps passed. This check deliberately invoked no actual agent, trusted
TEST executor or packaging executor, and granted no software verification outcome.
The repository working tree remained unchanged.

## Phase boundaries and limits

Phase 4 still owns NativeAgent/Codex execution, provider prompt construction,
process/artifact validation and independently fresh invocations. Phase 5 owns Git
workspaces/candidate creation; later phases own trusted TEST and semantic REVIEW.

Stage receipts are trusted orchestrator declarations. Their schemas, ordering and
Candidate identity are validated here; they do not prove a process ran, commands
passed, artifacts exist, review covers all criteria or elapsed budget was enforced.
No Run lifecycle or VERIFIED outcome is set by this routing engine. The future
orchestrator must establish execution facts before accepting receipts and persist
execution state/events through the later filesystem workflow layer.

Skills contain inline Markdown guidance and metadata, with no executable hooks or
independent executors. Optional external static bundle loading is not implemented;
compilation never silently follows mutable template/reference paths. A governed
activation/administration registry belongs to later product scope, not this PoC.

Methodology identities preserve exact digests even when labels are reused. A local
caller can supply changed bytes with an unchanged label, but those assets have a
different identity. This PoC does not implement a global immutable-version registry.

No Phase 3 acceptance blocker remains within the PoC scope.
