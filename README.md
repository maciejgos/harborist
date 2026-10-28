# Shipyard

Shipyard is a local, evidence-driven delivery harness for native coding agents. It turns an engineering request into an independently verified, revision-bound code candidate with durable evidence.

> **Status:** Phase 8 complete: synchronous CLI execution, revision-bound
> verification, bounded logs, shared budget accounting and terminal reports/evidence.
> Phase 9 baseline evaluation remains ahead.

## Git workspaces and candidates

```python
from pathlib import Path
from shipyard.domain import Attempt
from shipyard.git import GitRepository

repository = GitRepository(path=Path("/path/to/repository"))
attempt = Attempt.create(run_id, repository.resolve_base())
workspace = repository.create_workspace(attempt=attempt, path=Path("/path/to/build"))
# Pass workspace.path to execute_stage for BUILD; leave HEAD at start_sha.
candidate = workspace.publish_candidate()
```

Use the frozen contract base SHA when creating an actual Run's Attempt. The caller
validates Run/Attempt ownership and calls publication only after successful BUILD.
Workspace destinations must be fresh and outside the source checkout. Creation
checks out the exact start commit detached and preserves developer files/index.
BUILD must leave HEAD unchanged; Shipyard stages edits, deletions and nonignored
new files and creates the commit, including for a no-change result. Remove ignored
build residue explicitly before publication; it is never silently deleted.

The candidate remains reachable at `refs/shipyard/runs/<run-id>/candidate`.
Publication is create-only: an existing ref is never overwritten. A separate
checkout can use `candidate.candidate_sha` without access to the BUILD workspace.
Hooks and commit signing are disabled for harness operations. Errors raise
`GitWorkspaceError` and retain partial worktrees/commits for inspection. There is
no automatic cleanup or retry/ref replacement. The Run executor adds shared budget enforcement.
These synchronous operations assume a quiescent workspace and a local non-bare
source checkout; they provide isolation of state, not a security boundary.

See the [Phase 5 acceptance audit](spec/033-phase5-acceptance-audit/report.md).

## Development

Install [uv](https://docs.astral.sh/uv/), then run from the repository root:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

The project pins Python 3.14. uv will download it if needed. Domain contracts are
available through `shipyard.domain`; intake and inspection are available through
the CLI. Synchronous execution is available with `shipyard run <run-id>`.
The Run lifecycle acceptance contract is in
[spec/001-run-lifecycle/spec.md](spec/001-run-lifecycle/spec.md), alongside its
intake intent and implementation plan. VERIFIED completion now requires a
revision-bound validation record; see the Phase 7 API below.

`Attempt` identifies one execution within a Run and its starting commit.
`Candidate` identifies an owning Attempt and an exact resulting commit. Both are
immutable records; commit hashes accept full lowercase SHA-1 or SHA-256 syntax.
Commit resolution, isolated workspaces and candidate publication are available
through `GitRepository` and `GitWorkspace`. See the
[Attempt and candidate specification](spec/002-attempt-candidate-identity/spec.md)
for the acceptance contract, with intent and implementation guidance alongside it.

DESIGN, PLAN, BUILD, and REVIEW have immutable structured output contracts.
`parse_stage_result` validates a complete JSON document against its expected stage
without repairing output or inferring readiness from prose. REVIEW records an
exact Candidate and per-criterion assessments, with derived summary counts.
Process success, artifact existence, execution-context matching, and verification
remain separate responsibilities; parsing output does not advance a Run or grant
VERIFIED. See the
[stage-result specification](spec/003-stage-result-contracts/spec.md).

`ArtifactReference` records an immutable artifact version with Run/optional Attempt
ownership, kind, producing stage, SHA-256, and byte size. Its factory hashes exact
in-memory bytes without storing content or accessing files. Origin is declared
metadata; PACKAGE indexes stored files by exact byte size and digest. General lineage browsing remains out of scope. See the
[artifact identity specification](spec/004-artifact-identity/spec.md).

`RunEvent` and `AttemptCreatedEvent` describe lifecycle facts using immutable
validated snapshots. Factories generate event IDs and require explicit aware
timestamps, normalized to UTC. `DomainEvent` supports discriminated JSON validation
through Pydantic's `TypeAdapter`. Records do not emit events, establish historical
ordering, or change domain state; the filesystem Run store validates lifecycle event ordering. Full cancellation audit metadata remains out of scope. See the [domain event specification](spec/005-domain-events/spec.md).

## Capture a Run

The target repository must have a committed root `shipyard.yaml` with its mandatory
checks. Shipyard includes its own configuration. Choose operator settings with an
explicit model/profile and local playbook/skill sources; the examples freeze these
inputs without invoking the selected model.

```bash
uv run shipyard intake file:examples/intake/issue.md \
  --repo . --settings examples/intake/settings.yaml

uv run shipyard intake 'github:owner/repo#42' \
  --repo /path/to/target --settings /path/to/operator.yaml

uv run shipyard inspect RUN_UUID
uv run shipyard methodology RUN_UUID
uv run shipyard methodology RUN_UUID --stage build
```

Intake first validates methodology metadata, then prints a complete JSON contract
and leaves the Run in CREATED. It does not
execute agents or checks. Inspect validates the saved capture without consulting
original inputs. `methodology` previews the frozen playbook and skills as JSON;
`--stage` selects composed guidance for an agent stage. All commands accept
`--runs-dir`; intake also accepts `--ref`,
`--timeout` and `--verification-reserve`. Defaults are HEAD, 1800 seconds overall,
300 seconds reserved, and `~/.shipyard/runs`. A shorter timeout must still exceed
the reserve; override both when needed. Expected failures return nonzero status.
`uv run python -m shipyard --help` provides the same commands. See the
[CLI specification](spec/017-intake-cli/spec.md).

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
[Markdown intake specification](spec/007-markdown-intake/spec.md).

## GitHub Issue intake

`read_github_intent(run_id=run.run_id, source="github:owner/repo#42")` reads title,
body and labels once through authenticated local `gh`. Normalized intent contains
an H1 title, a sorted JSON array of label names, then the exact body. Comments are
excluded. Extra label transport metadata is ignored. `capture_intent` dispatches
both supported source forms, independently of the target repository.

Selectors are validated before launching `gh`. A missing executable, rejected
credentials/process failure, 30-second timeout, or malformed response raises
`GitHubIntakeError` with its cause. No GitHub write is performed. See the
[GitHub intake specification](spec/014-github-intake/spec.md).

## Intent persistence

Save a snapshot under an explicitly supplied Runs directory:

```python
from shipyard.persistence import FileIntentStore

store = FileIntentStore(root=Path(".shipyard/runs"))
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
[intent persistence specification](spec/008-intent-persistence/spec.md).

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
[Git base resolution specification](spec/009-git-base-resolution/spec.md).

## Frozen verification configuration

Target repositories commit a narrow `shipyard.yaml`:

```yaml
version: 1
checks:
  - id: tests
    command: pytest
```

Every listed check is mandatory. At least one check is required; IDs must be
unique and commands nonblank. Unknown fields, unsupported versions, duplicate YAML
keys, and unsafe object tags are rejected. Command strings retain their exact text.

```python
from shipyard.verification import load_verification_config

base_sha = repository.resolve_base()
verification = load_verification_config(repository=repository, base_sha=base_sha)
```

The loader reads the root `shipyard.yaml` from that exact commit, ignoring index
and working-tree edits. Its immutable snapshot retains validated settings, base
SHA, and a SHA-256 of the original file bytes. Git replacement refs cannot substitute
other content for committed-file reads. YAML source text is not retained.

`VerificationConfigError` reports read/parsing/validation failures with causes.
This loader does not execute checks or change Run outcomes. `execute_test` performs trusted TEST. See the [verification configuration specification](spec/010-verification-config/spec.md).

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
[execution snapshot specification](spec/012-execution-snapshot/spec.md).

## Complete Run persistence

`FileRunStore(root=Path(".shipyard/runs")).save(contract)` reserves a fresh Run
directory and stores `run.json` in CREATED, exact `intent.md`, `intent.json` and
`contract.json`. Contract JSON is written last as the completion marker. `load`
validates all four records and their agreement without reading original inputs.
Existing directories, including partial captures, raise `RunAlreadyExistsError`.

Read/write/validation failures raise `RunPersistenceError` with their causes.
Partial evidence is retained for inspection. To retry, create a new Run identity;
there is no automatic repair or overwrite and no multi-file atomicity/power-loss
guarantee. This store supports CREATED captures, not later lifecycle updates.
See [Run persistence specification](spec/015-run-contract-persistence/spec.md).

## Operator execution settings

`load_execution_settings(path=Path("operator.yaml"))` captures a version 1 YAML
file with `playbook` and `skills` source records (`name`, `version`, `path`), a
complete `agent_profile` (`name`, `version`, `provider`, `model`, `arguments`) and
`sandbox_policy: trusted-local`. Asset paths resolve beside the settings file.
Actual UTF-8 content and SHA-256 digests are frozen, so future file edits have no
live link to a snapshot. The agent model is an explicit operator choice.

Budget is excluded from YAML. Shipyard defaults to 1800 total seconds with 300
reserved for verification; callers may pass an explicit `ExecutionBudget` to the
loader. The target repository cannot set it. Unknown fields, duplicate YAML keys,
unsupported versions, invalid records and unreadable assets fail with
`SettingsError`. See [settings specification](spec/013-execution-settings/spec.md).

## Durable intake use case

`shipyard.application.create_run` accepts a source selector, `GitRepository`,
`FileRunStore`, a complete `ExecutionSnapshot`, and an optional base ref. It creates
an identity, resolves the base once, loads committed verification settings, captures
intent and saves the contract in CREATED. It first compiles all frozen methodology,
rejecting invalid topology or skill metadata before Git/source/storage I/O. An
explicitly supplied CREATED `Run` may be used instead. Errors propagate through the existing adapter boundaries.

The settings loader captures bytes; the application owns this methodology
validation gate. Historical captures remain inspectable without migration.
See [intake methodology validation](spec/024-intake-methodology-validation/spec.md).

The use case performs no agent calls or check execution. Invalid committed
configuration is rejected before source capture/storage. The synchronous executor maps later execution failures and produces terminal reports. See
[intake orchestration specification](spec/016-intake-orchestration/spec.md).

## Canonical playbook definition

`shipyard.domain.playbook.canonical_playbook(version="1")` returns an immutable
seven-stage definition with fixed dependencies and executor authority. TEST is
trusted Shipyard execution; agent stages require fresh invocations; REVIEW is
read-only and PACKAGE is outside budget. Modified/omitted stages or weakened
metadata are rejected. This defines topology without executing it. See
[canonical playbook specification](spec/019-canonical-playbook/spec.md).

## Frozen methodology documents

`shipyard.playbooks.parse_playbook` and `parse_skill` compile captured assets with
leading YAML front matter. Playbooks declare `id`, `version` and canonical `stages`;
skills declare `id`, `version`, `description` and their agent `stages`. Front-matter
identity must match the frozen asset. Skill metadata cannot declare dependencies,
executors or hooks. Bodies remain exact opaque guidance; no file or tool is read.

Document identities include kind, name, version and exact source SHA-256. Changed
bytes remain distinguishable even when a version label is reused. Legacy plain
Markdown captures can still be inspected, but compilation requires explicit front
matter. See [methodology document specification](spec/020-methodology-documents/spec.md).

## Stage guidance composition

`shipyard.skills.compile_methodology(execution)` parses all frozen methodology
inputs. `compose_guidance(compiled, stage=ArtifactStage.BUILD)` selects skills for
the requested agent stage in configured order. It returns immutable sections with
exact bodies, descriptions and content-bound identities. A stage may have no
matching skills. INTAKE/TEST/PACKAGE cannot receive agent skill composition.

Guidance is kept separate from the playbook's control metadata. Prose never
changes dependencies or executor authority. Phase 4 implements provider prompt
formatting and invocation. See [stage guidance specification](spec/021-stage-guidance/spec.md).

## Playbook routing

`PlaybookExecution(playbook=definition, attempt=attempt)` starts with INTAKE as its
next stage. `accept(StageReceipt(...))` returns a new immutable execution only when
the receipt matches the required stage and Candidate/Attempt identity. Successful
routing cannot skip TEST; a failed TEST routes to PACKAGE and blocks REVIEW.
Failures, cancellation and early exits also retain PACKAGE outside budget. PACKAGE
ends routing even if packaging fails. Validated JSON reloads enforce the same rules.

Receipts must come from trusted orchestration after actual executor validation.
They are declarations, not proof that checks ran or review passed; this engine
performs no I/O and does not grant VERIFIED. See the
[routing specification](spec/022-playbook-routing/spec.md).

## Bundled methodology

Shipyard includes canonical playbook v1 and engineering skill v2, scoped to all
four agent stages. The standalone files under `examples/intake`
match the package resources. `shipyard.skills.defaults.load_default_methodology()`
returns frozen assets independently of the caller's working directory; an explicit
agent profile is still required when adopting them into an execution snapshot.
No existing Run is migrated. See [bundled methodology specification](spec/023-bundled-methodology/spec.md).

## Saved methodology preview

`shipyard methodology RUN_UUID` loads the saved capture and prints compiled
playbook/skill metadata, guidance and exact content identities. Add `--stage build`
(or design/plan/review) for composed guidance. It never reads current methodology
files, executes stages or changes the saved contract. `inspect` remains available
for historical plain Markdown captures; `methodology` returns a compilation error
for those captures. See [preview specification](spec/025-methodology-preview/spec.md).

## Workflow

```text
INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE
```

The PoC implements independent Codex stages through a native-agent abstraction.
Its full workflow will combine:

- Markdown and GitHub Issue intake (implemented);
- isolated Git worktrees;
- deterministic checks defined in `shipyard.yaml`;
- independent semantic review;
- verification bound to an exact candidate commit;
- filesystem-backed evidence and reports.

The PoC runs synchronously on the developer's machine. It uses the local environment and does not provide hostile-code isolation.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Product Requirements Document](docs/Product%20Requirements%20Document%20v1.0.md)
- [Phase 1 acceptance audit](spec/006-phase1-acceptance-audit/report.md)
- [Phase 2 acceptance audit](spec/018-phase2-acceptance-audit/report.md)
- [Phase 3 acceptance audit](spec/026-phase3-acceptance-audit/report.md)
- [Phase 4 acceptance audit](spec/030-phase4-acceptance-audit/report.md)

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
not start or finish a Run. There is no `shipyard run` command yet.

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

The [Phase 4 audit](spec/030-phase4-acceptance-audit/report.md) records acceptance
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
Checks must leave the workspace clean, including ignored files, for REVIEW.
Shipyard retains residue for inspection rather than deleting it.

Commands are trusted local code. Standalone callers own total budget and lifecycle;
`execute_run` supplies a shared TEST deadline, records unstarted checks as timed out
after exhaustion, and owns Run accounting/finalization. Exclusive workspace use is required.
Captures are create-only, with partial failures retained and manifest written last;
this is not atomic publication or protection against malicious local processes.
See the [Phase 6 audit](spec/036-phase6-acceptance-audit/report.md).


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
[Phase 7 audit](spec/040-phase7-acceptance-audit/report.md).


## Synchronous execution and PACKAGE

New captures using the example settings adopt engineering guidance v2. BUILD can
return a bounded `process_report` with red/green command records and limitations.
Shipyard saves it as `build/build-process.json`, supplies it to REVIEW, and indexes
it in PACKAGE independently of diagnostic truncation. These records are explicitly
agent-reported: they cannot override trusted TEST or prove historical execution
order. Routine TDD policy stays in operating guidance; explicitly requested proof
still requires adequate evidence. Older captures/responses remain readable.
See the [process-evidence contract](spec/046-build-process-evidence/spec.md).

Capture a Run with `shipyard intake` as above, then execute its returned ID:

```bash
uv run shipyard run <run-id> --repo /path/to/repository --runs-dir /path/to/runs
```

`--workspace /fresh/path` overrides the default sibling `workspaces/<run-id>`
directory. The target repository must contain the frozen base commit. Codex must
already be installed and authenticated locally. Each native stage starts a fresh
process. Execution stays local and synchronous; Ctrl-C cancels the active executor
best-effort and packages a CANCELLED result. Exit codes are 0 for VERIFIED, 2 for
other completed software outcomes, 1 for execution or packaging failure, and 130
for cancellation. The command prints terminal Run JSON and absolute report/evidence
paths. `inspect` continues to return the frozen contract after execution.

The application entry point is `shipyard.application.execution.execute_run`, with
explicit `FileRunStore`, Run ID, `GitRepository`, fresh workspace and `NativeAgent`
parameters. Existing individual stage APIs remain available for lower-level use.

The frozen total budget starts at execution admission. DESIGN, PLAN and BUILD
share the allowance before the verification reserve; TEST and REVIEW share the
remaining total. Unused time rolls forward. Monotonic time controls deadlines;
UTC timestamps, measured durations and remaining budget are recorded for the Run
and stages. Native-agent deadlines use whole seconds, so less than one remaining
second cannot admit another agent. PACKAGE records its own timing outside that
allowance and remains available when remaining execution time is zero.

Run directories contain `run.json`, `contract.json`, `intent.*`, `attempt.json`,
`events.jsonl`, timing records, stage directories, `report.md`, and `evidence.json`.
DESIGN/PLAN/BUILD/REVIEW hold structured results, artifacts and bounded diagnostics;
TEST holds its complete check manifest and numbered logs. `invocation.json` records
log truncation and optional usage, including for provider process failure/timeout.
Partial captures lack their success manifest. `evidence.json` is published last and
indexes all prior files, including the report, by relative path, length and SHA-256.
It does not hash itself. Symlinks are rejected.

Provider-neutral usage supports optional input/output/cached tokens, bounded
provider metadata, and an actual reported charge with currency. The current Codex
adapter does not extract billing or token counters; usage/cost remain UNKNOWN.
There is no pricing table or estimated charge. Reports expose missing TEST/REVIEW
and unverified criteria rather than upgrading a failed outcome.

Execution and PACKAGE reserve their directories exclusively, preserve partial
failures and reject retries. Terminal records cannot be changed through the Run
store or executor. Lifecycle journals are validated on reload; a crash between
journal and snapshot writes fails closed. This is trusted-local persistence, not
power-loss atomicity, OS-enforced immutability or protection against manual edits.
A disk failure can prevent a report: PACKAGE errors are surfaced after terminal
persistence. Workspaces and candidate refs are retained for inspection; cleanup,
resume/recovery, SIGTERM handling, background service and concurrent writers are
out of scope. No live-provider evaluation is claimed.

See the [Phase 8 acceptance audit](spec/045-phase8-acceptance-audit/report.md).
