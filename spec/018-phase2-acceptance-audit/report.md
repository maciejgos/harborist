# Phase 2 acceptance audit

Date: 2026-10-26.

Result: **Phase 2 complete for the local synchronous PoC; ready for Phase 3.**

Audited implementation revision:
`d365af7344c34b60d7165a5304be359cca4dbe2b` (clean working tree).
The audit/documentation commit adds no executable-code changes. Historical
specifications 007–011 describe their original limited slices; specifications
012–017 explicitly extend that scope.

## Phase 2 requirement mapping

| PRD build item | Implemented evidence | Representative acceptance coverage |
|---|---|---|
| File issue adapter | `intake/markdown.py`, common `capture_intent` dispatch | `tests/intake/test_markdown.py`; `test_dispatch_preserves_markdown_without_imposing_metadata_schema` |
| GitHub issue adapter | `intake/github.py`, authenticated local gh, explicit source repository | `test_gh_capture_is_explicit_and_normalized`; `test_gh_failures_preserve_causes`; real subprocess capture in `test_github_capture_is_durable_after_issue_edit` |
| Intent normalization | Common immutable IntentSnapshot; GitHub title/body/sorted label names; exact local Markdown | GitHub normalization test and dispatch/front-matter preservation test |
| Base SHA resolution | System Git, resolve once in `application.create_run`, exact-commit configuration reads | `test_create_freezes_once_and_survives_all_mutable_inputs`; `test_explicit_ref_selects_older_committed_settings`; existing Git integration suite |
| Frozen configuration snapshot | Complete required execution settings plus committed verification snapshot in RunContract | Domain execution tests; settings capture tests; Run contract round-trip/mapping-order tests |
| intent.md | Create-only FileIntentStore composed by FileRunStore; validated content/metadata agreement | `test_round_trip_and_exclusive_creation`; invalid/disagreeing stored-record tests |

Both PRD Phase 2 acceptance statements pass:

1. **Deterministic serialization:** equivalent already-frozen values, including Run
   and artifact identities, serialize identically despite input mapping order and
   survive disk round-trips. See
   `test_equivalent_mapping_order_and_round_trip_are_deterministic` and
   `test_same_captured_inputs_produce_identical_contracts`. Creating another Run or
   recapturing an issue intentionally creates new identities; that is a different
   frozen input, not nondeterministic serialization of the same contract.
2. **Source edits cannot mutate a created Run:** saved Markdown survives deletion;
   a GitHub capture survives later Issue edits and removal of the fake gh
   executable. Reading a saved capture never re-fetches the Issue. Later config,
   methodology-file and branch changes cannot update immutable captured values.

## Frozen contract completeness

PRD §4.9 fields applicable to the PoC are represented:

- Input intent: exact UTF-8 Markdown and immutable artifact ownership/digest.
- Base Git SHA: one resolved full commit identity, bound to verification settings.
- Playbook and skill versions: explicit names/versions and actual content plus
  SHA-256; version labels alone cannot hide changed source bytes. Skill order is
  preserved and names must be unique. An explicitly empty skill list is valid.
- Agent profile: explicit name/version/provider/model/arguments, with no implicit
  model selection or provider calls during intake.
- Sandbox policy: the sole supported PoC policy, `trusted-local`, is explicit.
- Execution-semantic project configuration: the currently supported project
  configuration is the base-revision `shipyard.yaml` verification configuration;
  unsupported project fields are rejected rather than silently left unfrozen.
- Execution budget: Shipyard supplies 1800 seconds overall and 300 reserved for
  verification, or accepts explicit operator/application overrides. Budget cannot
  come from repository YAML. Runtime enforcement and PACKAGE handling are later
  execution work; PACKAGE remains outside the declared budget.

The Run remains CREATED. The intake API and CLI do not infer readiness, stage
success, candidate identity or verification from source prose.

## Validation observed

At the audited clean implementation revision:

- `uv run pytest -q`: **483 passed**.
- `uv run ruff check .`: **passed**.
- `uv run pyright`: **0 errors, 0 warnings**.
- Installed `shipyard --help` and module `python -m shipyard intake --help`: passed.
- Shipped settings and methodology assets load; root `shipyard.yaml` parses with
  three mandatory checks (tests, lint, types).

A writable UV_CACHE_DIR override was used for the local execution environment.
The checks were run directly; no trusted TEST stage exists yet and no domain
VERIFIED outcome is claimed.

Installed CLI smoke test against this repository's actual committed base:

1. Copy example issue/settings/playbook/skill into a temporary input directory.
2. Execute `uv run shipyard intake` targeting this repository, saving outside it.
3. Confirm the frozen base is exactly the audited SHA, three checks are captured,
   the default budget is frozen, and `run.json` remains CREATED.
4. Delete all copied source/settings/methodology files.
5. Execute `uv run shipyard inspect`; confirm identical complete contract JSON.

All five steps passed; the repository working tree remained unchanged.

## Limits and later-phase work

- GitHub parsing, exact command arguments, process errors and timeout are tested at
  the subprocess boundary; one integration uses an actual small fake executable.
  This audit did not perform a live authenticated GitHub request and does not
  certify a particular account's gh installation or credentials.
- Settings capture freezes methodology content; it does not interpret stage
  topology or compose skills. Phase 3 must validate/execute the canonical playbook
  and prevent mandatory-stage skipping. Frozen profile/model availability is
  checked when its provider adapter is implemented, not by Phase 2 intake.
- NativeAgent/Codex stage execution is Phase 4. Worktrees/candidate creation,
  trusted TEST and independent exact-revision REVIEW belong to later phases.
- Storage is create-only under the chosen Runs root. Partial directories remain
  inspectable and block retries with the same identity. There is no overwrite,
  automatic repair, multi-file atomic publication or power-loss guarantee.
- Loading validates schema, nested digests and record agreement. The local
  filesystem is trusted; this is not cryptographic protection against someone
  deliberately rewriting all persisted records consistently.
- Later lifecycle/event persistence, execution-failure outcomes/reports and budget
  enforcement remain future work. Intake failures propagate typed errors without
  claiming a completed workflow or producing a terminal execution report.

No Phase 2 acceptance blocker remains within the PoC scope.
