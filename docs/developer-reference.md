# Developer reference

[Documentation index](README.md) · [Architecture](../ARCHITECTURE.md)

Run the examples from the repository root. Lower-level APIs require explicit
ownership of orchestration and lifecycle. Snippets build on earlier variables
and are not standalone scripts.
Use the [CLI usage guide](usage.md) for ordinary execution.

## Contents

- [Domain records](#domain-records)
- [Git workspaces and candidates](#git-workspaces-and-candidates)
- [Markdown intake](#markdown-intake) and [GitHub intake](#github-issue-intake)
- [Intent persistence](#intent-persistence) and [Run persistence](#complete-run-persistence)
- [Git base resolution](#git-base-resolution) and [frozen contracts](#frozen-run-contract)
- [Durable intake](#durable-intake-use-case)
- [Native-agent stages](#independent-native-agent-stages-phase-4)
- [Trusted TEST](#trusted-test) and [independent REVIEW](#independent-review-and-verified)
- [Module implementation details](#implementation-details-by-module)
- [Candidate application](#candidate-application-implementation)

## CLI organization

`cli/__init__.py` registers commands. Dedicated `intake`, `inspection`, `run` and
`apply` modules own their handlers, while `cli/capture.py` shares source capture
preparation and execution-command rendering. Installed and module entry points
continue to use the same `app`.

## Domain records

The Run lifecycle acceptance contract is in
[spec/001-run-lifecycle/spec.md](../spec/001-run-lifecycle/spec.md), alongside its
intake intent and implementation plan. VERIFIED completion now requires a
revision-bound validation record; see [independent REVIEW](#independent-review-and-verified).

`Attempt` identifies one execution within a Run and its starting commit.
`Candidate` identifies an owning Attempt and an exact resulting commit. Both are
immutable records; commit hashes accept full lowercase SHA-1 or SHA-256 syntax.
Commit resolution, isolated workspaces and candidate publication are available
through `GitRepository` and `GitWorkspace`. See the
[Attempt and candidate specification](../spec/002-attempt-candidate-identity/spec.md)
for the acceptance contract, with intent and implementation guidance alongside it.

DESIGN, PLAN, BUILD, and REVIEW have immutable structured output contracts.
`parse_stage_result` validates a complete JSON document against its expected stage
without repairing output or inferring readiness from prose. REVIEW records an
exact Candidate and per-criterion assessments, with derived summary counts.
Process success, artifact existence, execution-context matching, and verification
remain separate responsibilities; parsing output does not advance a Run or grant
VERIFIED. See the
[stage-result specification](../spec/003-stage-result-contracts/spec.md).

`ArtifactReference` records an immutable artifact version with Run/optional Attempt
ownership, kind, producing stage, SHA-256, and byte size. Its factory hashes exact
in-memory bytes without storing content or accessing files. Origin is declared
metadata; PACKAGE indexes stored files by exact byte size and digest. General lineage browsing remains out of scope. See the
[artifact identity specification](../spec/004-artifact-identity/spec.md).

`RunEvent` and `AttemptCreatedEvent` describe lifecycle facts using immutable
validated snapshots. Factories generate event IDs and require explicit aware
timestamps, normalized to UTC. `DomainEvent` supports discriminated JSON validation
through Pydantic's `TypeAdapter`. Records do not emit events, establish historical
ordering, or change domain state; the filesystem Run store validates lifecycle event ordering. Full cancellation audit metadata remains out of scope. See the [domain event specification](../spec/005-domain-events/spec.md).

## Git workspaces and candidates

```python
from pathlib import Path
from shipyard.application.candidate_message import candidate_message
from shipyard.domain import Attempt
from shipyard.git import GitRepository

repository = GitRepository(path=Path("/path/to/repository"))
attempt = Attempt.create(run_id, repository.resolve_base())
workspace = repository.create_workspace(attempt=attempt, path=Path("/path/to/build"))
# Pass workspace.path to execute_stage for BUILD; leave HEAD at start_sha.
# intent is the frozen Run contract's IntentSnapshot.
candidate = workspace.publish_candidate(
    message=candidate_message(intent=intent, attempt=attempt)
)
```

Use the frozen contract base SHA when creating an actual Run's Attempt. The caller
validates Run/Attempt ownership and calls publication only after successful BUILD.
Workspace destinations must be fresh and outside the source checkout. Creation
checks out the exact start commit detached and preserves developer files/index.
BUILD must leave HEAD unchanged; Shipyard stages edits, deletions and nonignored
new files and creates the commit, including for a no-change result. Publication
removes ignored disposable files (including local environments and tool caches)
from the owned isolated worktree before committing. Keep durable implementation
files tracked or nonignored; ignored files are not candidate inputs. The source
checkout is never cleaned.

The application composes the message from the frozen intake source before the
initial candidate commit. For a GitHub source `github:acme/source#42`:

```text
Shipyard candidate for acme/source#42

Run: cd736d82-fa33-42a2-9e50-fb9e561aa015
Attempt: 9518caf4-4d86-41ba-8641-0ea452a587c1
```

The source issue may belong to a different repository from the target checkout.
The reference is informational; candidate publication does not close the issue.
File sources use the same complete identity fields without an issue reference:

```text
Shipyard candidate

Run: cd736d82-fa33-42a2-9e50-fb9e561aa015
Attempt: 9518caf4-4d86-41ba-8641-0ea452a587c1
```

The Git boundary accepts the finished message through the required `message`
argument. It does not interpret source selectors or fetch issue metadata. TEST and
REVIEW evaluate the original message-bearing candidate SHA without rewriting it.

The candidate remains reachable at `refs/shipyard/runs/<run-id>/candidate`.
Publication is create-only: an existing ref is never overwritten. A separate
checkout can use `candidate.candidate_sha` without access to the BUILD workspace.
Hooks and commit signing are disabled for harness operations. Errors raise
`GitWorkspaceError` and retain partial worktrees/commits for inspection. There is
no automatic worktree removal or retry/ref replacement. The Run executor adds shared budget enforcement.
These synchronous operations assume a quiescent workspace and a local non-bare
source checkout; they provide isolation of state, not a security boundary.

See the [Phase 5 acceptance audit](../spec/033-phase5-acceptance-audit/report.md).

## Markdown intake

Capture a local issue file through the Python API:

```python
from pathlib import Path

from shipyard.domain import Run
from shipyard.intake import read_markdown_intent

run = Run.create()
intent = read_markdown_intent(run_id=run.run_id, path=Path("issue.md"))
```

`IntentSnapshot` preserves exact UTF-8 content, including front matter, BOM, and
line endings, with a validated artifact digest/size and resolved source reference.
Later file edits or deletion do not change the snapshot. Empty content is accepted;
actionability is a later DESIGN decision. `MarkdownIntakeError` wraps file and
UTF-8 decoding errors with their original causes.

This API returns an in-memory capture and leaves the Run unchanged. Optional YAML
front matter is retained as source text rather than interpreted. Common source
dispatch and GitHub normalization are implemented. See the
[Markdown intake specification](../spec/007-markdown-intake/spec.md).

## GitHub Issue intake

`read_github_intent(run_id=run.run_id, source="github:owner/repo#42")` reads title,
body and labels once through authenticated local `gh`. Normalized intent contains
an H1 title, a sorted JSON array of label names, then the exact body. Comments are
excluded. Extra label transport metadata is ignored. `capture_intent` dispatches
both supported source forms, independently of the target repository.

Selectors are validated before launching `gh`. A missing executable, rejected
credentials/process failure, 30-second timeout, or malformed response raises
`GitHubIntakeError` with its cause. No GitHub write is performed. See the
[GitHub intake specification](../spec/014-github-intake/spec.md).

## Intent persistence

Save a snapshot under an explicitly supplied Runs directory:

```python
from shipyard.persistence import FileIntentStore

store = FileIntentStore(root=Path.home() / ".shipyard" / "runs")
store.save(intent)
restored = store.load(intent.run_id)
```

Each Run gets `<root>/<run-id>/intent.md` with exact UTF-8 content and `intent.json`
with source/artifact metadata. Loading validates content digest, size, and Run
ownership without consulting the original issue. Artifact identities are preserved.

Saves are create-only: any existing intent file causes `IntentAlreadyExistsError`,
even for identical content. Metadata is written last. Failed writes may leave
partial files; subsequent loads reject them and saves preserve them for inspection.
`IntentPersistenceError` wraps I/O and invalid stored-data failures with causes.

This store does not provide full Run persistence, automatic repair, atomic
multi-file publication, or power-loss durability guarantees. See the
[intent persistence specification](../spec/008-intent-persistence/spec.md).

## Git base resolution

Resolve committed HEAD or a native Git commit-ish through system Git:

```python
from shipyard.git import GitRepository

repository = GitRepository(path=Path("."))
base_sha = repository.resolve_base()
earlier_sha = repository.resolve_base(ref="HEAD~1")
```

The adapter returns a validated full commit SHA, accepts commit tags and native
revision expressions, and rejects non-commit targets. It preserves developer
branches, index, and working files. Repository-scoped environment overrides are
cleared in the subprocess while normal Git configuration is retained.
`GitResolutionError` preserves launch/process/output failures as causes.

Each explicit call resolves afresh. The intake use case resolves once and
persists the SHA; this adapter does not freeze a Run contract, create worktrees,
or manage candidate commits/refs. See the
[Git base resolution specification](../spec/009-git-base-resolution/spec.md).

## Frozen Run contract

Compose the previously captured inputs without repeating intake or Git resolution:

```python
from shipyard.configuration import load_execution_settings
from shipyard.domain import RunContract

execution = load_execution_settings(path=Path("examples/intake/settings.yaml"))
contract = RunContract(
    run_id=run.run_id,
    intent=intent,
    base_sha=base_sha,
    verification=verification,
    execution=execution,
)
serialized = contract.model_dump_json()
restored_contract = RunContract.model_validate_json(serialized)
```

The immutable contract requires matching intent Run ownership and verification
base SHA. Equivalent validated values, including the same existing identities,
produce identical compact JSON regardless of input mapping key order. Exact
Markdown, check order, command text, and provenance survive round-trips.

The required `ExecutionSnapshot` freezes playbook/skill names, versions, exact
content and SHA-256 digests, an explicit agent profile, trusted-local policy, and
an execution budget with a verification reserve. Skill names must be unique;
only the canonical `bounded-repository-change` playbook is supported. Empty skill
lists are explicit. The reserve must be positive and smaller than the total.

This domain record performs no I/O or execution and does not grant verification.
Old partial contracts without execution settings are rejected. Intake orchestration
and the CLI connect these boundaries. See the
[execution snapshot specification](../spec/012-execution-snapshot/spec.md).

## Complete Run persistence

`FileRunStore(root=Path.home() / ".shipyard" / "runs").save(contract)` reserves a fresh Run
directory and stores `run.json` in CREATED, exact `intent.md`, `intent.json` and
`contract.json`. Contract JSON is written last as the completion marker. `load`
validates all four records and their agreement without reading original inputs.
Existing directories, including partial captures, raise `RunAlreadyExistsError`.

Read/write/validation failures raise `RunPersistenceError` with their causes.
Partial evidence is retained for inspection. To retry, create a new Run identity;
there is no automatic repair or overwrite and no multi-file atomicity/power-loss
guarantee. `save` creates CREATED captures; `begin` and `finish` own later lifecycle updates.
See [Run persistence specification](../spec/015-run-contract-persistence/spec.md).

## Durable intake use case

`shipyard.application.create_run` accepts a source selector, `GitRepository`,
`FileRunStore`, a complete `ExecutionSnapshot`, and an optional base ref. It creates
an identity, resolves the base once, loads committed verification settings, captures
intent and saves the contract in CREATED. It first compiles all frozen methodology,
rejecting invalid topology or skill metadata before Git/source/storage I/O. An
explicitly supplied CREATED `Run` may be used instead. Errors propagate through the existing adapter boundaries.

The settings loader captures bytes; the application owns this methodology
validation gate. Historical captures remain inspectable without migration.
See [intake methodology validation](../spec/024-intake-methodology-validation/spec.md).

The use case performs no agent calls or check execution. Invalid committed
configuration is rejected before source capture/storage. The synchronous executor maps later execution failures and produces terminal reports. See
[intake orchestration specification](../spec/016-intake-orchestration/spec.md).

## Independent native-agent stages (Phase 4)

`shipyard.application.stages.execute_stage` executes one stage synchronously.
It accepts a reloaded `RunContract`, its `Attempt`, an existing workspace,
explicit upstream artifact paths, a new output directory outside the workspace,
an injected `NativeAgent`, and positive `remaining_seconds`. For example:

```python
from pathlib import Path
from shipyard.agents.codex import CodexAgent
from shipyard.application.stages import execute_stage
from shipyard.domain.attempt import Attempt
from shipyard.domain.run_contract import RunContract
from shipyard.domain.stage_result import AgentStage

contract = RunContract.model_validate_json(Path("contract.json").read_bytes())
attempt = Attempt.create(contract.run_id, contract.base_sha)
result = execute_stage(
    contract=contract,
    attempt=attempt,
    stage=AgentStage.DESIGN,
    workspace=Path("/absolute/path/to/prepared/workspace"),
    upstream={},
    output_dir=Path("/absolute/path/to/new/design-capture"),
    agent=CodexAgent(),
    remaining_seconds=300,
)
```

The caller prepares the workspace and calculates remaining budget. This API does
not start or finish a Run. Use `shipyard run` for synchronous orchestration.

| Stage | Durable upstream inputs | Captured Markdown |
|---|---|---|
| DESIGN | Frozen contract intent | `spec.md` |
| PLAN | Frozen intent, `spec.md` | `plan.md` |
| BUILD | Frozen intent, `spec.md`, `plan.md` | Optional revised `plan.md` |
| REVIEW | `spec.md`, `test-evidence.json`; frozen intent is also supplied | `review.md` |

Pass upstream files as a mapping from the names above to explicit paths. Frozen
intent is supplied from the contract; an optional `intent.md` path must match it
exactly. Original input bytes are checked after invocation. BUILD returns plan
revisions into its new capture, preserving earlier versions, and cannot rewrite
the authoritative upstream spec. An invalid invocation leaves its partial capture
without `manifest.json`; retry with a new directory.

REVIEW additionally requires `candidate` and a trusted successful TEST
`StageReceipt` for that exact candidate. Its Attempt must match, and the existing
workspace must be clean at the exact candidate SHA before and after execution.
Untracked and ignored files are rejected for REVIEW. The supplied evidence must be
a complete `execute_test` manifest matching the frozen configuration, Run, Attempt,
candidate, ordered commands/results and receipt. Missing or contradictory evidence
is rejected before invocation. Complete criterion coverage is checked afterward;
only Shipyard's validated decision can authorize VERIFIED completion.

Each successful directory contains `request.json` (frozen input text, guidance,
profile and candidate context), `stage-result.json`, its Markdown outputs, and a
completion `manifest.json` with Run/Attempt ownership and artifact digests/sizes.
Directories are create-only; inputs and failed captures are never overwritten.

`CodexAgent` starts a fresh `codex exec --ephemeral --ignore-user-config` for each
call, sends the prompt on stdin, and uses a stage-specific `--output-schema` and
fresh `--output-last-message` file. It requests read-only access for DESIGN, PLAN
and REVIEW, workspace-write for BUILD, and no approval prompts. Markdown is
returned inside the final JSON envelope and written by Shipyard. Provider output
has `result`, `artifact` and `plan_update` fields; `artifact` is null for BUILD,
and `plan_update` is null except when BUILD revises the plan.

The frozen profile must use `provider: codex`. `model` is explicit. Initially,
profile `arguments` supports only pairs such as
`["--config", 'model_reasoning_effort="high"']` (also `-c`), with effort values
minimal/low/medium/high/xhigh. Other arguments are rejected before launch to
preserve Shipyard's workspace, output and invocation controls. Authentication
comes from the operator's local Codex installation; no provider secrets are saved.
The adapter enforces the supplied per-call timeout, kills its process group on
timeout, bounds final output to 4 MiB and retains at most 64 KiB per diagnostic stream. Launch errors,
nonzero exits, missing/invalid final messages and invalid stage contracts fail the
stage. The synchronous Run executor maps failures and invokes PACKAGE.

The [Phase 4 audit](../spec/030-phase4-acceptance-audit/report.md) records acceptance
evidence. Tests use a fake provider executable with real subprocesses and Git;
a live authenticated provider call has not been validated. CLI flag references:
[official Codex commands](https://learn.chatgpt.com/docs/developer-commands#codex-exec).

## Trusted TEST

```python
from shipyard.application.verification import execute_test

tested = execute_test(
    contract=contract, attempt=attempt, candidate=candidate,
    workspace=workspace.path, output_dir=Path("/path/to/test-capture"),
    check_timeout_seconds=60,
)
# Pass tested.receipt and test-capture/manifest.json to REVIEW only on success.
```

TEST uses the frozen base configuration, even if BUILD changes `shipyard.yaml`.
Every command runs in order through `/bin/sh -c`; nonzero exits, launch errors
and timeouts do not skip subsequent checks. Each command has its own explicit
timeout. Output is drained continuously with a 64 KiB retained prefix per stream
and explicit truncation flags in numbered stdout/stderr files; the create-only
manifest records all results, configuration provenance and exact candidate receipt.
Evidence must be outside the workspace. Wrong identity or dirty/wrong revision
is rejected before running; a changed workspace after checks yields TEST_FAILED.
The Run executor removes ignored files generated by checks before the final
cleanliness assertion and REVIEW. BUILD environments are removed before TEST,
so checks must provision their dependencies from the candidate and operator
environment. Check failures remain failures after cleanup. Tracked changes and
nonignored untracked files are retained and produce TEST_FAILED. Nested Git
repositories are not forcibly deleted; remaining residue fails closed.
Standalone `execute_test` callers retain the strict no-residue behavior unless
they explicitly supply an owned-workspace cleanup callback.

Commands are trusted local code. Standalone callers own total budget and lifecycle;
`execute_run` supplies a shared TEST deadline, records unstarted checks as timed out
after exhaustion, and owns Run accounting/finalization. Exclusive workspace use is required.
Captures are create-only, with partial failures retained and manifest written last;
this is not atomic publication or protection against malicious local processes.
See the [Phase 6 audit](../spec/036-phase6-acceptance-audit/report.md).


## Independent REVIEW and VERIFIED

The PoC requires explicit acceptance declarations in `spec.md`. Every declared
criterion is required, with a unique ID containing at least three digits:

```markdown
- AC-001: A concrete observable requirement.
## AC-002 — Another required behavior
AC-003: A required failure path.
```

Fenced examples and inline prose references do not declare criteria. Empty specs,
empty declarations and duplicate IDs are rejected. The spec reference hashes exact
UTF-8 content, including line endings. REVIEW returns exactly those IDs once each
with `pass`, `fail` or `unverified`; omitted or unknown IDs are invalid stage output.
The reviewer explains assessments and unverified areas in `review.md`.

```python
from shipyard.application.stages import execute_stage
from shipyard.domain import AgentStage

reviewed = execute_stage(
    contract=contract, attempt=attempt, stage=AgentStage.REVIEW,
    workspace=workspace.path,
    upstream={"spec.md": spec_path, "test-evidence.json": test_manifest_path},
    output_dir=Path("/path/to/review-capture"), agent=agent,
    remaining_seconds=60, candidate=candidate, test_receipt=tested.receipt,
)
decision = reviewed.review_decision
assert decision is not None
completed = running_run.complete(
    decision.outcome, verification=decision.verification,
)
```

All required criteria must PASS and all mandatory checks must pass for VERIFIED.
Any FAIL or UNVERIFIED yields CHANGES_REQUIRED. Failed TEST prevents REVIEW.
The stage manifest includes the decision, spec reference, TEST capture digest and,
for VERIFIED, a validation record binding Run, Attempt, candidate, frozen check
configuration/results and complete REVIEW. `Run.complete(VERIFIED)` without that
record fails; construction and JSON reload enforce the same rules. Records remain
bound to their recorded SHA, and cannot verify a later revision.

These are trusted local harness attestations, not cryptographic proof of execution.
Operators must use authentic captures and exclusive workspaces. The harness checks
consistency but does not authenticate hand-edited local files. Semantic PASS remains
the independent reviewer's assessment. `execute_run` persists completed states and
lifecycle events, accounts for the shared budget and packages evidence. See the
[Phase 7 audit](../spec/040-phase7-acceptance-audit/report.md).



## Implementation details by module

### `domain`

Owns stable product concepts:

```text
Run
Attempt
RunContract
Candidate
StageResult
IntentSnapshot
RunOutcome
FailureReason
ExecutionBudget
```

**Invariant:** domain code does not depend on CLI, Codex-specific details, GitHub transport, or filesystem layout.

The implemented `RunContract` is a frozen execution contract, separate from
Run lifecycle state. It composes existing `run_id`, `IntentSnapshot`, `base_sha`,
`VerificationConfigSnapshot`, and `ExecutionSnapshot`, rejecting mismatched intent
ownership or verification base SHA. Construction performs no I/O and generates no identities.
Existing Pydantic JSON APIs preserve values and serialize equivalent validated
inputs deterministically, including their existing identities. Matching provenance
is a consistency check; committed-content reading remains the loader's job.

Execution snapshots require actual methodology text with SHA-256 digests, explicit
names/versions, a canonical playbook, unique skill names, an agent profile,
trusted-local policy and a budget with a verification reserve. They declare frozen
inputs consumed by the Phase 3 methodology compiler and guidance/routing layers;
the snapshot itself performs no engine logic or executor invocation.
Intake orchestration and CLI persist these inputs, completing the Phase 2 frozen
contract. This record alone does not execute a Run.

### `intake`

The Markdown adapter resolves a local path, reads bytes once, strictly decodes
UTF-8, and returns a validated in-memory `IntentSnapshot`. It preserves the source
text, including front matter, BOM, and line endings, and records resolved source
provenance. Filesystem/decoding failures retain their causes in
`MarkdownIntakeError`.

The snapshot has no live dependency on the source file. The adapter performs no
writes or Run transitions; the intent store handles persistence separately.
Common source dispatch accepts file and GitHub selectors. GitHub captures title,
body and labels once through authenticated gh, normalizing title/sorted label names
and preserving body text. Comments are excluded. Optional local front matter stays
source text; no schema is imposed. Source and target repositories are independent.

### `configuration`

Operator YAML is loaded into a complete immutable execution snapshot. Methodology
paths resolve beside the settings file and exact UTF-8 content is hashed. Safe
unique-key YAML parsing is shared with verification configuration. Budget cannot
be specified in YAML: Shipyard supplies defaults or an explicit application budget.
Intake CLI defaults to the single `shipyard.settings.yaml` at the resolved target
checkout root, selected by `--repo` or `.` from the invocation directory. Git
resolves the root when either directory is a subdirectory. Explicit `--settings
PATH` takes precedence, including external files; relative explicit paths use
the invocation directory. No recursive search, global/home fallback, merging,
automatic creation, or migration is performed. Missing, unreadable, or invalid
selected settings fail before Run creation with the selected path and remediation
to supply `--settings PATH`; an invalid explicit override never falls back.

Execution settings are local intake inputs independent of `--ref`. Root
`shipyard.yaml` remains separate and supplies mandatory checks from the frozen
base SHA. Settings cannot replace these checks or weaken TEST/REVIEW gates.
Existing Runs consume captured execution and methodology snapshots without
rediscovering or reloading live files.

### `application`

The implemented `create_run` composes source capture, one base resolution, committed
verification loading and complete contract storage through explicit parameters. It
returns a durable CREATED capture without agent/check execution. Non-CREATED
inputs and capture failures are rejected. New intake compiles all frozen
methodology before external I/O, rejecting legacy plain assets or weakened topology.
Historical captures remain inspectable without being silently migrated. The
implemented `execute_stage` invokes one injected NativeAgent using durable
upstream artifacts and frozen methodology. It writes create-only per-stage
captures with a manifest last, rejects upstream mutation, and requires a complete
matching trusted TEST capture and successful receipt plus clean exact-candidate
workspace for REVIEW. It returns a validated REVIEW decision without advancing
lifecycle or routing. `execute_run` composes these stages with Git workspaces,
candidate publication, trusted TEST, shared monotonic budget accounting, validated
routing, lifecycle/event persistence and PACKAGE. Early software outcomes, failed
checks, invalid output, provider failures, cancellation and budget exhaustion each
produce an explicit terminal state. Unexpected executor exceptions produce
INTERNAL_ERROR. Failed TEST never invokes REVIEW. PACKAGE runs outside admission
checks. The executor preserves workspaces and rejects any second admission;
there is no retry/recovery or background service.
Before lifecycle admission it checks repository availability, the exact frozen
commit, and fresh workspace placement outside the resolved checkout. Invalid
paths leave the capture CREATED. New captures select
`<effective-runs-root>/<run-id>/workspace`, changing the separate workspace tree
introduced in #5. `FileRunStore.save` writes versioned, Run-bound
`workspace-layout.json` before publishing the contract; this non-contract policy
also covers application captures. Missing layout information means legacy;
invalid or foreign layout records fail closed, without backfilling old captures.
An explicit `--workspace` has precedence, followed by a recorded selection
(`execution-workspace.json` or retained `workspace.json`), then the capture's
default. Legacy CREATED Runs without a recorded selection
retain `~/.shipyard/workspaces/<run-id>` as their default. Existing historical
worktrees remain in place and fail freshness checks, never being reused or moved.
`--runs-dir` selects storage and thus the new Run-owned default, subject to the
existing execution-context consistency checks. No override relocates a capture
or rewrites a frozen contract. A default inside the resolved source checkout is
rejected before admission with an instruction to supply a fresh external
`--workspace`; no fallback is selected.

Application placement policy permits only the dedicated workspace child beneath
Runs storage. It rejects stage/evidence locations, sibling Runs, ancestors
containing records, collisions (including dangling symlinks), inaccessible parents,
and source overlap in either direction, including aliases. Required parents are
prepared before admission. Placement is rechecked immediately before creation,
and Git rechecks source/freshness constraints. Later creation failures preserve
partial data and terminal failure semantics. `execution-workspace.json` records
the actual resolved admitted path with Run/Attempt ownership before worktree creation;
CLI execution JSON, stderr summaries, terminal reports and evidence expose it.
Historical evidence without that information stays readable with an unknown path.

Each explicit intake creates a distinct Run and fresh workspace even when issue
identity and intent digest match. Executing a captured Run never recaptures the
issue. There is no deduplication, deletion, automatic migration or source candidate
application. Source repositories stay in place, including linked-worktree metadata
and Shipyard candidate refs. Agents, staging, publication and ignored-file cleanup
operate on the workspace child, leaving sibling records untouched. This remains
trusted-local operational isolation, not an adversarial filesystem sandbox.

### `playbooks` / `skills`

Playbooks decide **which stages run**. The implemented immutable
`PlaybookDefinition` fixes all seven stages, predecessor dependencies, executor
authority, fresh agent invocation, read-only REVIEW and PACKAGE outside budget.
The `canonical_playbook` factory requires an explicit version. These declarations
do not execute stages. Skills provide **stage-specific guidance** and contain no
executable hooks in the PoC.

Methodology compilation reads only frozen asset content. Validated YAML front
matter binds playbook identity/topology or skill identity/description/agent-stage
scope. Unknown skill control fields are rejected; opaque body prose has no
workflow authority. Content-bound identities include exact source SHA-256.
Legacy Phase 2 plain Markdown is inspectable, but cannot compile as methodology
without an explicit front-matter migration.

`compile_methodology` parses a frozen execution snapshot; `compose_guidance` filters
skills by native-agent stage in configured order and returns immutable sections
with exact content/provenance. Shipyard-owned stages do not receive composed agent
skills. Guidance cannot add steps, dependencies, executors or hooks; provider prompt
formatting and execution are implemented by the Phase 4 Codex adapter.

`PlaybookExecution` is a pure immutable routing engine bound to one Attempt.
Validated harness receipts advance only the next canonical stage. BUILD binds the
Candidate; TEST and REVIEW must retain its exact identity. Failures and early exits
route to PACKAGE; a failed TEST cannot reach REVIEW. PACKAGE ends routing even on
failure. History is validated again on JSON reload. This does not prove executor
success, run checks, enforce elapsed budget or grant a Run outcome.

Canonical playbook v1 and engineering skill v2 Markdown are packaged resources.
`load_default_methodology` captures and validates them independently of cwd.
Operators still explicitly choose their agent profile; default adoption never
mutates a previously captured Run.

### `review` / verification gate

`extract_criteria` reads explicit `AC-NNN: text` declarations (also Markdown list
items or headings with an em dash), ignoring fenced examples and prose references.
READY DESIGN output is validated before PLAN: missing, duplicate or empty
acceptance declarations produce INVALID_STAGE_OUTPUT. Clarification output does
not require acceptance declarations. Every declared criterion is required;
`SpecificationReference` binds unique IDs to exact spec UTF-8 SHA-256.

REVIEW preflight reconciles complete TEST captures with frozen check configuration,
ordered commands, identities and computed success; receipts alone are insufficient.
`evaluate_review` requires exact candidate and spec coverage. Any FAIL/UNVERIFIED
produces CHANGES_REQUIRED; all PASS plus successful TEST produces a domain
`VerificationRecord`. The stage manifest captures that decision and TEST digest,
alongside review.md and structured results. Invalid coverage leaves no success
manifest. Failed TEST blocks invocation.

`Run.complete` accepts VERIFIED only with matching verification. The immutable
record checks Run/Attempt/candidate ownership, complete passing check evidence and
exact all-PASS criterion coverage, also on JSON reload. No evidence transfers to a
new SHA. This is trusted-local consistency validation, not authentication of
arbitrary files or proof of the reviewer's semantic correctness. The synchronous executor owns lifecycle
persistence and orchestration; lower-level stage APIs retain explicit caller ownership.

### `agents`

`NativeAgent.execute(AgentRequest)` is a small synchronous port with no session
continuity API. Requests carry stage, workspace, frozen profile/guidance, upstream
text, remaining seconds and REVIEW candidate; outputs separate process status
from structured final JSON. Parsing reuses existing stage contracts and rejects
missing Markdown, wrong stages, foreign candidates and unauthorized plan changes.
Empty or whitespace-only intent is preserved for DESIGN to assess actionability;
generated upstream artifacts must remain nonblank.

`CodexAgent` uses one fresh ephemeral `codex exec` subprocess per invocation with
explicit model, workspace, sandbox and schema. It reads only the final message,
not stdout, and bounds its size. Read-only stages return Markdown inside JSON for
Shipyard to persist. BUILD uses workspace-write. Profile arguments cannot override
harness controls; only reasoning-effort config pairs are initially supported.
Timeouts terminate the process group best-effort; temporary files are cleaned.
The shared subprocess capture drains pipes while retaining a 64 KiB prefix per
stream, flags truncation, and closes inherited pipes without waiting for detached
descendants. Diagnostics survive nonzero exits, deadlines, and missing, oversized
or invalid UTF-8 final messages in partial captures.
Optional validated usage belongs to the NativeAgent response, never the agent
output envelope; the Codex adapter currently reports no usage/billing counters.
Authentication stays in the local Codex environment; no live-provider smoke test
is claimed by the synthetic process integration suite.

**Invariant:** vendor-specific behavior stays behind `NativeAgent`.

### `git`

`GitRepository` retains the public adapter methods. `git/application.py` composes
application validation and branch transactions behind that facade; shared subprocess
transport and environment handling live in `git/command.py`, with shared failures
in `git/errors.py`. This keeps transaction details separate from repository reads
and candidate publication without changing their callers.

The implemented `GitRepository` resolves a supplied repository's committed HEAD
or explicit native Git commit-ish to a full validated SHA. It invokes system Git
via a subprocess argument list with commit peeling and option termination.
Repository-scoped environment overrides are cleared in a copy, normal configuration
is preserved, and optional locking is disabled. The resolution operation performs no checkout,
fetch, reset, commit, or ref update and preserves dirty developer state.

Each call resolves afresh. Run creation must call once and persist
the resulting immutable base SHA. Workspace/candidate operations are described below.

`read_file_at_commit` reads repository-root-relative blob bytes at a validated
actual commit SHA without consulting mutable refs or checkout files. Git replacement
handling is disabled for object type/content reads so the requested original
commit cannot silently supply replacement configuration. Read failures preserve
their causes in `GitReadError`.

The implemented Git boundary owns:

- base ref resolution to immutable `base_sha`;
- isolated worktree creation;
- candidate commit creation;
- candidate ref management.

`require_normal_index_tracking` rejects assume-unchanged and skip-worktree flags
that could hide tracked edits. Candidate publication checks this before staging;
every exact-revision cleanliness check and checked-out application preflight also
enforces it. Shipyard rejects these flags without changing the index itself.

`require_clean_revision` provides a read-only pre/post REVIEW assertion for an
existing checkout at the exact candidate SHA, rejecting tracked, untracked and
ignored workspace changes. It performs no checkout or candidate creation.

`create_workspace(attempt, path)` creates a fresh detached worktree at the exact
Attempt start SHA outside the source checkout. `GitWorkspace.publish_candidate(message=...)`
accepts the final message composed by the application from frozen intake provenance
and Run/Attempt identities. The Git adapter does not interpret source selectors.
Publication requires unchanged detached HEAD, stages BUILD changes and creates a commit with
explicit harness identity, disabled hooks/signing and a clean-revision assertion.
Ignored disposable files are removed from the owned detached linked worktree
before publication using system Git clean (ignored files only, without forcing
nested-repository removal). The source checkout is never cleaned. The Run-owned candidate ref is
published with atomic create-only update-ref; existing refs cannot be overwritten.
Failures retain partial state for inspection. Replacement objects are disabled.
The caller validates ownership and BUILD success; no lifecycle grant is implied.
Workspaces require exclusive sequential use; cleanup and retry remain caller-owned.

Local uncommitted developer state is ignored.

### `verification`

The implemented loader reads root `shipyard.yaml` from an exact supplied base SHA,
parses UTF-8 YAML using safe unique-key mappings, and validates frozen domain
settings. Version 1 contains only ordered checks with unique IDs and nonblank
command strings; all checks are mandatory. Snapshots retain the base SHA and
source-byte SHA-256 without source text, generated identities, or timestamps.

Missing/invalid configuration or zero checks raises `VerificationConfigError`
synchronously. `run_checks` executes every frozen command through the local POSIX shell,
collecting exit status, timeout/launch errors and file logs without fail-fast.
`application.execute_test` guards exact candidate cleanliness before and after
execution, persists configuration/results/receipt with a manifest last, and emits
TEST_FAILED on check failure or post-check workspace changes. The Run executor
injects its isolated-workspace cleanup function to remove ignored files generated
by TEST before asserting cleanliness; lower-level callers default to retaining
all residue. BUILD's ignored environments are removed before publication, so TEST
cannot depend on those uncommitted inputs. Tracked and nonignored changes still
fail closed, and REVIEW retains the strict no-residue assertion. It does not reread
candidate configuration. Callers still own total budget accounting and lifecycle
mapping, including configuration failures to Run `CONFIGURATION_ERROR`. The synchronous executor supplies one shared TEST
deadline: after exhaustion remaining checks are recorded without invocation.
Log truncation does not affect check success.

**Invariant:** model output can never override a failed trusted check.


## Candidate application implementation

`shipyard apply <run-id> --branch <existing-local-branch> [--repo PATH]
[--runs-dir PATH]` is an independent synchronous operation after PACKAGE. The
canonical [stage flow](../ARCHITECTURE.md#execution-flow) is unchanged. VERIFIED remains the software outcome;
new terminal summaries say “Verified; awaiting application” and print a
shell-quoted command with an explicit branch placeholder. JSON stdout retains
its `run`, `workspace`, `report`, `evidence` contract; guidance goes to stderr.
Application does not invoke agents or rerun verification.

`application/context.py` shares saved-locator resolution between run and apply.
Default storage is `~/.shipyard/runs`; custom storage needs `--runs-dir`. Valid
context selects the repository independently of cwd, and explicit options must
match after path/checkout normalization. Invalid existing locators fail closed;
only absence permits legacy explicit repository or cwd/default storage fallback.

`evidence/application.py` reads the immutable index, validates canonical relative
paths, regular files, lengths and SHA-256 digests, and reconciles frozen capture,
lifecycle, Attempt, stage captures, specification, TEST and REVIEW with terminal
verification. Retained workspace files and HEAD are excluded from eligibility.
`domain/application.py` describes versioned receipts independently of I/O.
`application/apply.py` sequences validation, Git preflight, receipt preparation,
expected-old advancement, final SHA confirmation and receipt publication.

The existing system-Git adapter requires actual original base/candidate commit
objects and the matching Run-owned candidate ref. Only existing local branches
are eligible. Ahead/divergent targets need a new Run. A checked-out target requires
clean tracked, staged, untracked and ignored state and no in-progress Git operation.
Another worktree occupying the branch blocks advancement and is identified in the
error. Unoccupied branches use expected-old update-ref without changing checkout
files. Checked-out advancement prepares a ref transaction, holds the target lock
while two-tree read-tree updates index/files, then commits the ref transaction.
Hooks and replacement objects are disabled. Other branches/checkouts are preserved;
there is no reset, clean, stash, force-update, commit creation or automatic rollback.
Already-equal targets are validated no-ops, even with dirty files.

`persistence/application.py` reserves each target operation using a nonblocking
filesystem lock. Durable preparation precedes mutation. Create-only receipts live
outside packaged Runs at `<runs-root>/applications/<run-id>/<target-key>.json`;
the key hashes normalized repository and full branch name. Each receipt records
Run, candidate, repository, branch, previous/resulting SHA and zoned timestamp.
Separate targets do not overwrite receipts and repetition reuses the original.
Preparation (`.pending.json`) and post-Git confirmation (`.confirmed.json`) files
remain for recovery; staged publication flushes file data and syncs the directory.

Failures after possible mutation return nonzero with observed target SHA,
receipt/preparation locations and retry guidance. Users inspect state, resolve
obstructions and retry the same command. Retry revalidates everything and can
complete a missing receipt without a second advance. With no durable confirmation
of earlier advancement, equality produces an observed-no-op receipt with equal
previous/resulting SHAs. Success requires a durable receipt and confirmed target.
Run artifacts remain byte-for-byte immutable; receipts are not verification
evidence. Full transactions across Git and storage, power-loss atomicity and
concurrent external checkout writers are outside the PoC guarantees.
