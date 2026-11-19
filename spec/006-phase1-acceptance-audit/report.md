# Phase 1 acceptance audit

## Verdict

The domain building blocks are ready for the next bounded development slice.
Full Phase 1 acceptance is **PARTIAL**: three of its five acceptance criteria
are demonstrated at the domain level; revision-bound verification and fresh
Attempts during actual rework/recovery have only prerequisite models/tests.

Recommend beginning Phase 2 with Markdown intake and an immutable intent
snapshot, keeping the unresolved acceptance claims open. Intake depends on the
existing identity/artifact contracts, not completed verification or recovery
execution. This is a dependency-readiness recommendation, not a declaration that
Phase 1 is fully accepted or an authorization to waive requirements.

## Baseline and method

- Audited SHA: `37c9fbed47aea7868a7729155d1586c1c1acc272`.
- Audit started: `2026-10-25T18:42:39Z`.
- Preexisting working-tree changes: none; `git status --short` was empty.
- Inspected: every module under `src/harborist/`, all five domain test files,
  `pyproject.toml`, ARCHITECTURE.md, slice specifications 001–005, and PRD section
  97 Phase 1. PRD §§24–25, 65, 68–69, 89.2, and later implementation phases
  provide scope and allocation context.
- Assessment changes: this directory and a README link only. Code, tests,
  configuration, earlier specifications, and the PRD remain at the baseline.

All source/test links below refer to files as inspected at this SHA. Use
`git show <audited-sha>:<path>` to retrieve that exact historical version after
future changes. Parametrized pytest function selectors identify all collected
cases of that function. This report is a manual assessment, not Harborist TEST or
an independent native-agent REVIEW, and does not confer VERIFIED status.

Statuses: **PASS** means directly supported within the stated requirement scope;
**PARTIAL** means some prerequisites/behavior exist without full proof;
**FAIL** means an observed contradiction; **UNVERIFIED** means evidence cannot
establish a conclusion. Disposition and proposed implementation phase are separate
from status. No FAIL finding was observed; this does not establish unimplemented
execution behavior.

## Validation results

Commands ran from the repository root with a writable uv cache override because
the sandbox cannot use the default cache. The override changes cache location,
not project configuration or check selection.

| Exact command | Exit | Observed result |
|---|---|---|
| `UV_CACHE_DIR=/private/tmp/harborist-uv-cache uv run pytest` | 0 | 320 collected, 320 passed; no warnings reported |
| `UV_CACHE_DIR=/private/tmp/harborist-uv-cache uv run ruff check .` | 0 | All checks passed |
| `UV_CACHE_DIR=/private/tmp/harborist-uv-cache uv run pyright` | 0 | 0 errors, 0 warnings, 0 informations |

pytest reported Python 3.14.7 and pytest 9.1.1. Pyright is configured in strict
mode over source and tests. These results establish the existing validation
baseline, not execution safety, coverage completeness, or an operational PoC.

## Requirement traceability

Requirement wording follows [PRD §97 Phase 1](../../docs/Product%20Requirements%20Document%20v1.0.md#phase-1--domain-foundation).
Evidence labels resolve to source symbols and runnable test selectors below.

### Building blocks

PASS here means the domain building block exists with demonstrated local
behavior; limitations do not silently become product capabilities.

| ID | Building block | Status | Evidence and demonstrated behavior | Limit / disposition |
|---|---|---|---|---|
| P1-B01 | Run | PASS | E1: `Run.create`, validated immutable transitions, identity preservation | No Run orchestration, frozen contract, or persistence yet; later slices |
| P1-B02 | Attempt | PASS | E2: `Attempt.create`, Run ownership and exact starting SHA | Creation records only; no execution, recovery, or ownership lookup; F2 |
| P1-B03 | Lifecycle/outcome model | PASS | E1: separate lifecycle, outcome, and failure enums; validated combinations | Synchronous PoC omits QUEUED as recorded in slice 001; no queue behavior claimed |
| P1-B04 | Immutable IDs | PASS | E1–E5: frozen Run/Attempt/Candidate/artifact/event records; factories create fresh UUID4s | Candidate identity is Attempt ID plus SHA; global UUID uniqueness is not enforced by storage |
| P1-B05 | Artifact identities | PASS | E4: ownership/origin records, SHA-256 and byte size, exact in-memory hashing | No storage, loading, retention, or durable integrity verification; F3 |
| P1-B06 | Candidate identity | PASS | E3: Candidate requires owning Attempt and full validated commit hash | Syntax does not establish a real Git commit/ref or trusted execution identity; F1 |
| P1-B07 | Event model | PASS | E5: Run lifecycle and Attempt-created snapshots, UTC time, discriminated JSON | Records do not emit, order, persist, or replay events; F3 |
| P1-B08 | Stage contracts | PASS | E6: four native-agent outputs, stage/status validation, REVIEW criteria and derived counts | Domain declarations only; process/artifact/context checks and trusted TEST are later integration; F1/F4 |

### Acceptance criteria

| ID | PRD acceptance criterion | Status | Evidence and demonstrated behavior | Limit / disposition |
|---|---|---|---|---|
| P1-A01 | Invalid state transitions are rejected | PASS | E1: all five lifecycle states against four operations; unsupported operations raise `InvalidRunTransition` | Domain API only; does not test a nonexistent executor |
| P1-A02 | Candidate verification always references a SHA | PARTIAL | E3/E6: Candidate and REVIEW declarations require full SHA; E1 rejects VERIFIED | No authoritative TEST/REVIEW binding or successful verification result exists. Missing behavior cannot be passed vacuously; F1 |
| P1-A03 | Lifecycle and outcome are distinct | PASS | E1: `TEST_FAILED` completes a Run; execution failure requires a failure reason; inconsistent combinations rejected | Does not establish workflow-level outcome selection |
| P1-A04 | Cancellation is terminal | PASS | E1: CANCELLED rejects start/complete/fail/cancel; E5 represents the terminal fact | Full cancellation execution/audit is not demonstrated; F5 |
| P1-A05 | Rework/recovery create new Attempt identities | PARTIAL | E2: repeated creation for the same Run/start yields distinct UUID4s | No rework/recovery action exists, so those paths are not tested; F2 |

### Prohibited coupling

E7 is source inspection evidence. No architectural import-enforcement tests were
added; these PASS findings describe the current revision, not future enforcement.

| ID | Prohibition | Status | Evidence | Limit / disposition |
|---|---|---|---|---|
| P1-D01 | No GitHub SDK types in core entities | PASS | E7: annotations/imports use stdlib, Pydantic, and local domain types | Recheck when issue/GitHub adapters arrive |
| P1-D02 | No Docker types in core entities | PASS | E7: no Docker dependency or annotations | PoC makes no sandbox-security claim |
| P1-D03 | No GCS types in core entities | PASS | E7: artifact references have no provider/storage fields | Recheck when persistence adapters arrive |
| P1-D04 | No Codex-specific types in core entities | PASS | E7: stage contracts are provider-neutral | NativeAgent and the Codex adapter are not implemented |

The 17 rows above contain 15 PASS and 2 PARTIAL findings. No FAIL or UNVERIFIED
row was needed: the two unimplemented acceptance paths have demonstrable
prerequisites, so PARTIAL is the appropriate status. Row counts are not a score
or a basis for overriding the unresolved acceptance criteria.

## Evidence index

The pytest selectors below were covered by the full successful run. They can also
be passed to `uv run pytest <selector>` for targeted reproduction.

### E1 — Run lifecycle, outcomes, and immutability

Source: [run.py](../../src/harborist/domain/run.py), `Run.validate_state`,
`Run.create`, `start`, `complete`, `fail`, `cancel`, `_require_source`, and the
three enums.

- `tests/domain/test_run.py::test_creation`
- `tests/domain/test_run.py::test_transition_matrix`
- `tests/domain/test_run.py::test_inconsistent_state_is_rejected`
- `tests/domain/test_run.py::test_completion_outcomes`
- `tests/domain/test_run.py::test_failure_reasons`
- `tests/domain/test_run.py::test_fields_are_frozen`
- `tests/domain/test_run.py::test_json_validation_rejects_invalid_completion`

These assert fresh/preserved IDs, terminal rejection, distinct software/execution
outcomes, and rejection of VERIFIED through completion, construction, and JSON.
They do not prove a future executor uses these APIs correctly.

### E2 — Attempt creation and ownership

Source: [attempt.py](../../src/harborist/domain/attempt.py), `Attempt.create`
and `create_candidate`.

- `tests/domain/test_attempt_candidate.py::test_fresh_attempts_and_candidate_ownership`
- `tests/domain/test_attempt_candidate.py::test_every_field_is_required_and_frozen`

Repeated factory calls preserve Run/start identity while producing distinct
Attempt IDs. They are not calls to real rework/recovery paths.

### E3 — Candidate and revision syntax

Source: [candidate.py](../../src/harborist/domain/candidate.py), `Candidate`;
[revision.py](../../src/harborist/domain/revision.py), `GitCommitSha`.

- `tests/domain/test_attempt_candidate.py::test_commit_hash_constraints`
- `tests/domain/test_attempt_candidate.py::test_constructors_and_factories_apply_hash_validation`
- `tests/domain/test_attempt_candidate.py::test_json_applies_hash_validation`
- `tests/domain/test_attempt_candidate.py::test_full_hashes_across_constructors_helpers_and_json`
- `tests/domain/test_attempt_candidate.py::test_records_do_not_enforce_repository_or_uniqueness_rules`

These prove full lowercase SHA-1/SHA-256 syntax and explicit ownership. They do
not resolve Git objects, keep candidates reachable, or attach authoritative checks.

### E4 — Artifact identity

Source: [artifact.py](../../src/harborist/domain/artifact.py), `ArtifactReference`
and its factory, kind/stage enums, and digest constraints.

- `tests/domain/test_artifact.py::test_known_content_vectors`
- `tests/domain/test_artifact.py::test_independent_records_can_share_content_identity`
- `tests/domain/test_artifact.py::test_exact_bytes_are_not_normalized`
- `tests/domain/test_artifact.py::test_direct_construction_and_json_round_trip`
- `tests/domain/test_artifact.py::test_every_field_is_frozen`

Factory hashing measures supplied bytes. Declared origin and directly supplied
metadata do not establish storage integrity, execution, or authenticity.

### E5 — Event records

Source: [event.py](../../src/harborist/domain/event.py), `RunEvent`,
`AttemptCreatedEvent`, `DomainEvent`, and `_as_utc`.

- `tests/domain/test_event.py::test_run_event_factory`
- `tests/domain/test_event.py::test_run_event_rejects_mismatched_snapshot`
- `tests/domain/test_event.py::test_attempt_creation_event`
- `tests/domain/test_event.py::test_timestamp_normalizes_to_utc`
- `tests/domain/test_event.py::test_run_event_round_trip`
- `tests/domain/test_event.py::test_event_fields_and_ownership_properties_are_immutable`

These validate snapshot declarations, time normalization, IDs, and immutability.
They do not establish that an operation occurred, emission followed it, or a record
was durably appended.

### E6 — Native-agent output contracts

Source: [stage_result.py](../../src/harborist/domain/stage_result.py),
the four stage-result models, `ReviewStageResult.validate_unique_criteria`,
`summary`, and `parse_stage_result`.

- `tests/domain/test_stage_result.py::test_stage_status_matrix`
- `tests/domain/test_stage_result.py::test_parser_rejects_unexpected_stage`
- `tests/domain/test_stage_result.py::test_parser_rejects_without_repair`
- `tests/domain/test_stage_result.py::test_parser_wraps_schema_errors`
- `tests/domain/test_stage_result.py::test_build_cannot_assert_candidate`
- `tests/domain/test_stage_result.py::test_review_requires_assessment_fields`
- `tests/domain/test_stage_result.py::test_invalid_review_candidate`
- `tests/domain/test_stage_result.py::test_review_summary`

REVIEW's ready status describes a finished assessment, including FAIL/UNVERIFIED
entries. No test establishes completeness against a frozen spec, actual process
success, or correspondence to a trusted execution Candidate.

### E7 — Dependency boundaries and implementation inventory

All eight files under `src/harborist/domain/`, plus `src/harborist/__init__.py`,
were inspected. Imports are exclusively stdlib, Pydantic, and local domain
modules; annotations contain no provider-specific types. pyproject.toml declares
Pydantic as its only runtime dependency. No dynamic provider-loading code was
found. Source inventory contains no application, Git, verification, agent,
intake, or persistence implementation.

Reproducible inspection commands:

```bash
rg --files src/harborist
rg -n '^(from|import) ' src/harborist
```

The import search supports the full source inspection; a keyword search alone
would not prove these boundaries. Approved slice contracts explicitly identify
the domain-only scope: [001](../001-run-lifecycle/spec.md),
[002](../002-attempt-candidate-identity/spec.md),
[003](../003-stage-result-contracts/spec.md),
[004](../004-artifact-identity/spec.md), and [005](../005-domain-events/spec.md).

## Gaps and follow-ups

These are recommended allocations, not new approvals or changes to the PRD.
They remain open after this assessment.

| ID | Related finding | Missing behavior/evidence | Recommended phase | Completion condition |
|---|---|---|---|---|
| F1 | P1-A02; B06/B08 | Trusted candidate creation, TEST evidence, exact REVIEW binding, and a positive verification decision | Phases 5–7 | Tests run authoritative checks against the exact created commit; reject stale/mismatched SHA, mandatory failures, and missing/FAIL/UNVERIFIED required criteria; only complete valid evidence permits VERIFIED |
| F2 | P1-A05; B02 | Rework/recovery entry points that allocate fresh Attempts and preserve lineage | Phase 11 | Tests exercise both actions, proving new IDs under the same Run, correct starting revision, no resumed failed sessions, and no inherited candidate verification |
| F3 | B05/B07 | Artifact loading/integrity, event emission and filesystem persistence, terminal evidence immutability | PoC orchestration/persistence slices alongside Phases 2–8 | Integration tests establish persisted records/artifacts, digest verification on load, correct event creation after operations, and rejected terminal evidence mutation |
| F4 | B08 | Process success, required semantic artifacts, and execution-context validation | Phase 4 and Phases 6–7 | Executor tests reject unsuccessful processes/missing artifacts, never infer workflow state from prose, and prevent REVIEW after mandatory TEST failure |
| F5 | P1-A04 scope limit | Cancellation actor/reason/stage audit, active process termination, and bounded evidence finalization | PoC cancellation/orchestration work as execution becomes available; scheduling/sandbox behavior remains later product work | Tests prove active work is stopped best-effort, Run remains terminal, cancellation context is recorded, and evidence is finalized without treating cancellation as execution failure |

PRD §97 places verification execution in Phases 5–7 and rework/recovery in
Phase 11, while listing their invariants as Phase 1 acceptance claims. PRD §89.2
also excludes actual rework/recovery from the PoC. The current models support
those invariants but do not demonstrate the execution claims. The appropriate
assessment is PARTIAL, with the wording/allocation tension explicit, rather than
expanding this audit into implementation or changing the phase gate.

Event delivery/storage and full cancellation orchestration are scope limitations,
not contradictions of the passing domain-record/terminal-state findings. PoC
persistence must remain filesystem-based; no database, worker, or event-bus
infrastructure is required by these follow-ups.

## Next bounded step

Domain building-block readiness: **ready for dependent intake work**.
Full Phase 1 acceptance: **PARTIAL, P1-A02 and P1-A05 still open**.
Phase 2 readiness: **recommend beginning a separately specified Markdown intake
and immutable intent snapshot slice**.

That slice should demonstrate source edits cannot mutate captured intent. It
does not yet complete Phase 2's frozen base/configuration contract. Keep GitHub
intake, base resolution, and full contract serialization as subsequent bounded
items. Any formal decision to accept the Phase 1 gate with downstream dependencies
outstanding is outside this assessment-only report.
