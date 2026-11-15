# Shipyard CLI reference

A standalone reference for the commands available in this checkout. The
[Codex CLI command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
inspires the command overview, option tables and examples; all functionality
below belongs to Shipyard's registered CLI.

## Command overview

| Command | Purpose |
| --- | --- |
| [intake](#intake) | Freeze a request without executing it. |
| [inspect](#inspect) | Validate and print a saved contract. |
| [methodology](#methodology) | Preview frozen playbook and skills. |
| [run](#run) | Capture a source or submit a saved Run; optionally execute in the foreground. |
| [rework](#rework) | Create a fresh Attempt against the frozen spec. |
| [recover](#recover) | Explicitly recover an eligible execution failure. |
| [apply](#apply) | Advance an existing local branch to a verified candidate. |
| [runs](#runs) | List saved history and service submissions. |
| [status](#status) | Inspect a Run and optionally wait for completion. |
| [web](#web) | Serve the local browser workspace. |
| [publish](#publish) | Publish an explicitly approved candidate to a GitHub PR. |
| [github-status](#github-status) | Fetch and save GitHub collaboration evidence. |
| [cancel](#cancel) | Record cancellation through the service. |
| [supersede](#supersede) | Replace a Run with a new captured request. |
| [service](#service) | Manage the serial background execution service. |
| [service serve](#service-serve) | Run the service in the current process. |
| [service start](#service-start) | Start the service detached. |
| [service status](#service-status) | Read service health. |
| [service stop](#service-stop) | Request graceful drain and shutdown. |

## Invocation and conventions

```text
shipyard [ROOT_OPTIONS] COMMAND [ARGUMENTS] [OPTIONS]
```

From the development checkout, install dependencies with `uv sync` and prefix
invocations with `uv run`, for example `uv run shipyard --help`. An installed
`shipyard` executable uses the same arguments without that prefix.

Uppercase names such as `RUN_ID`, `CANDIDATE_SHA`, `ATTEMPT_ID` and `PATH` are
placeholders to replace, not literal values. `RUN_ID` and `ATTEMPT_ID` are UUIDs;
`CANDIDATE_SHA` and `PREVIOUS_SHA` are full Git commit SHAs. Brackets in syntax
mean optional arguments and are not typed. `OPTIONS` means options listed for
that entry. All options are optional unless marked **required**. No short aliases
are registered. Every command and group accepts `--help`, a flag that prints
help and exits without performing that command; it is omitted from repeated
tables below. Boolean flags default to false unless stated otherwise.

| Root option | Type / default | Meaning |
| --- | --- | --- |
| `--help` | Flag; false | Show root help and exit. |
| `--install-completion` | Flag; false | Install completion for the current shell. |
| `--show-completion` | Flag; false | Print completion for the current shell for copying or customization. |

Root completion options take no shell argument. Use `shipyard COMMAND --help`
or `shipyard service SUBCOMMAND --help` for scoped help. Running the root or
`service` without a command displays help.

### Sources and frozen capture

Both source forms are supported wherever `SOURCE` is accepted:

- `file:path/to/issue.md`: a nonempty path to a readable local Markdown request.
- `github:owner/repo#number`: a GitHub Issue with a positive issue number;
  requires installed, authenticated `gh` and access to that repository.

Quote the whole argument when it contains spaces or shell-sensitive characters:

```bash
uv run shipyard intake 'file:requests/fix login.md'
uv run shipyard intake 'github:owner/repo#42'
```

Capture freezes intent, the resolved base SHA, methodology, agent settings,
verification configuration and execution budget. It reads operator settings from
`shipyard.settings.yaml` at the target checkout root, even when invoked from a
subdirectory. An explicit `--settings PATH` takes precedence; relative explicit
paths resolve from the invocation directory. Methodology paths resolve beside
the selected settings file. Invalid or missing settings fail without searching
other locations. Mandatory checks come from `shipyard.yaml` in the frozen base.
Executing agent stages requires an installed, authenticated Codex CLI and a
usable target Git repository.

A saved Run UUID uses its existing frozen contract: execution does not recapture
source or reload a new contract. New requests require new capture. Examples in
this document are separate scenarios with the stated prerequisites, not a
sequence that can be run against any arbitrary Run.

### Storage, context and service selection

`--runs-dir PATH` selects filesystem Runs storage (default `~/.shipyard/runs`).
It does not select the background service. `--control-dir PATH` selects that
service's control directory (default `~/.shipyard/control`). Use the same custom
control directory for service management, submission and viewers.

For commands using execution context (`run`, continuations, `apply`, publication
and supersession), saved `execution-context.json` selects the repository and
Runs root independently of the current directory. Where supported, explicit
`--context PATH` takes precedence over automatic lookup at
`RUNS_ROOT/RUN_ID/execution-context.json`; supplied `--repo` and `--runs-dir`
are constraints and must agree. Custom storage requires its locator; there is
no global discovery. Only an absent automatic context allows legacy repository
fallback to `--repo` or the current directory and default storage. An invalid
existing locator fails closed without repair.

## intake

Capture a CREATED Run and print its ID, repository, base, source and a command
for later execution. This performs no agents or verification checks.

```text
shipyard intake SOURCE [OPTIONS]
```

| Argument / option | Type / default | Meaning and constraints |
| --- | --- | --- |
| `SOURCE` | String; **required** | Either [source form](#sources-and-frozen-capture). |
| `--settings PATH` | Path; selected checkout's `shipyard.settings.yaml` | Operator override; resolution follows the capture rules above. |
| `--repo PATH` | Path; `.` | Target implementation checkout; its root is selected. |
| `--ref REF` | String; `HEAD` | Base commit-ish, resolved once at capture. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Capture storage root. |
| `--timeout SECONDS` | Integer ≥ 1; `1800` | Overall execution budget. |
| `--verification-reserve SECONDS` | Integer ≥ 1; `300` | Verification reserve; must be strictly less than timeout. |
| `--json` | Flag; false | Print full frozen contract JSON to stdout; execution hint goes to stderr. |

For a configured target checkout and readable request:

```bash
uv run shipyard intake file:requests/fix.md --repo /path/to/repo --ref main
# Replace RUN_ID with the ID printed above; start the service first.
uv run shipyard run RUN_ID
```

## inspect

Validate and print a saved frozen contract as JSON without rereading its original
inputs. Inspection does not execute, modify or verify the Run.

```text
shipyard inspect RUN_ID [OPTIONS]
```

| Argument / option | Type / default | Meaning |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Existing saved Run. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Storage containing the capture. |

```bash
uv run shipyard inspect RUN_ID
```

## methodology

Compile and preview the saved playbook and skills as JSON, without execution or
Run modification. This does not establish verification.

```text
shipyard methodology RUN_ID [OPTIONS]
```

| Argument / option | Type / default | Meaning |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Existing saved Run. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Capture storage. |
| `--stage STAGE` | Enum; omitted | Select composed guidance for a stage; otherwise print full methodology. Accepted values: `intake`, `design`, `plan`, `build`, `test`, `review`, `package`. |

The parser accepts every stage listed above, but guidance composition succeeds
only for `design`, `plan`, `build` and `review`. Selecting `intake`, `test` or
`package` reports an error because those are not native-agent stages. No selection
runs an executor.

```bash
uv run shipyard methodology RUN_ID --stage build
```

## run

Capture a source and submit it, or submit an existing CREATED Run. Background
submission is the default and requires a running local service. Exit zero means
durable acceptance, not VERIFIED. Closing the submitting terminal leaves
execution running. One service runs one Run at a time through the synchronous
`INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE` workflow.

```text
shipyard run SOURCE_OR_RUN_ID [OPTIONS]
```

| Argument / option | Type / default | Meaning and constraints |
| --- | --- | --- |
| `SOURCE_OR_RUN_ID` | String; **required** | A supported source or saved Run UUID (help calls this `run_id`). |
| `--settings PATH` | Path; omitted | Source capture only; effective default is checkout-root settings. Rejected with a UUID. |
| `--ref REF` | String; omitted → `HEAD` | Source capture only; rejected with a UUID. |
| `--timeout SECONDS` | Integer ≥ 1; omitted → `1800` | Source capture only; rejected with a UUID. |
| `--verification-reserve SECONDS` | Integer ≥ 1; omitted → `300` | Source capture only, strictly less than timeout; rejected with a UUID. |
| `--repo PATH` | Path; omitted | Source target defaults to `.`; for a saved Run, constrains saved context or supplies legacy fallback. |
| `--runs-dir PATH` | Path; omitted → `~/.shipyard/runs` | Capture storage or automatic context lookup root; must match context. |
| `--context PATH` | Path; omitted | Explicit saved execution-context locator; only for UUID execution, rejected with a source. |
| `--workspace PATH` | Path; omitted | Fresh isolated Git worktree location; see placement below. |
| `--foreground` | Flag; false | Execute synchronously in this terminal instead of queuing. No service required. |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Service selector in background mode; unused in foreground mode. |
| `--json` | Flag; false | Background: delivery record. Foreground: result containing Run, workspace, report and evidence paths. |

Default workspace selection respects a saved selection/layout; new captures use
their dedicated `RUNS_ROOT/RUN_ID/workspace`, while legacy captures can use
`~/.shipyard/workspaces/RUN_ID`. Overrides must be fresh, writable and isolated
from the source checkout. Runs storage must not overlap an override: only the
Run's dedicated workspace child may reside inside controlled Run records. Do
not use a workspace path that contains Runs storage or aliases another Run.

If capture succeeds but submission/preflight fails, the CREATED capture is
retained; correct the problem and submit its UUID instead of recapturing. An
execution already admitted is not automatically retried. Use explicit
continuation for eligible failures.

Foreground mode writes progress to stderr and a terminal summary or JSON to
stdout. Its exit codes are `0` for VERIFIED, `2` for other software outcomes,
`1` for execution/finalization errors, and `130` for cancellation (PACKAGE
interruption can be an error). Verification belongs only to the exact candidate
SHA and never applies it automatically.

With valid target settings and a running service:

```bash
uv run shipyard run 'github:owner/repo#42' --repo /path/to/repo
uv run shipyard run file:requests/fix.md --repo /path/to/repo
# A separate saved CREATED Run, with custom capture storage:
uv run shipyard run RUN_ID --runs-dir '/path/to/saved runs'
```

For synchronous execution of a separate saved CREATED Run:

```bash
uv run shipyard run RUN_ID --foreground --json --workspace /path/to/fresh-worktree
```

## rework

Create a fresh Attempt beginning at PLAN against the previous packaged candidate,
then BUILD, fresh trusted TEST and independent REVIEW. Normal eligibility is a
completed `TEST_FAILED` or `CHANGES_REQUIRED` outcome with a candidate and validated
frozen spec. Explicit selected GitHub feedback also permits a VERIFIED
predecessor. The spec and original contract remain frozen; incompatible feedback
requires rescoping through a new Run. No verification or native session is inherited.

```text
shipyard rework RUN_ID [OPTIONS]
```

| Argument / option | Type / default | Meaning and constraints |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Run whose latest Attempt is eligible. |
| `--feedback TEXT` | String; empty | Human feedback to PLAN; at most 32,768 characters including selected GitHub feedback. |
| `--additional-seconds N` | Integer ≥ 0; `0` | Explicit additional Run budget grant. |
| `--repo PATH` | Path; omitted | Saved-context constraint or legacy repository fallback. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Context lookup/storage root. |
| `--context PATH` | Path; omitted | Explicit saved context; [precedence rules](#storage-context-and-service-selection) apply. |
| `--workspace PATH` | Path; omitted | Fresh worktree override; same placement constraints as `run`. Default later-Attempt workspace is `RUNS_ROOT/../workspaces/RUN_ID/ATTEMPT_ID`. |
| `--foreground` | Flag; false | Execute synchronously; otherwise submit to the service. |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Background service selector; unused in foreground. |
| `--json` | Flag; false | Background delivery JSON; foreground Run/Attempt and report/evidence paths. |
| `--expected-attempt UUID` | UUID; current latest Attempt | Reject if the predecessor changed before admission/execution. |
| `--observation PATH` | Path; omitted | Saved GitHub observation for this Run; requires `--feedback-id`. |
| `--feedback-id ID` | Repeatable string; none | Explicit review/comment IDs from the observation (such as `review:123`, `inline:456` or `comment:789`); requires `--observation`; 1–32 selections. |

Continuation uses cumulative spending across Attempts and adds only explicit
grants. Remaining allowance must exceed the frozen verification reserve; increase
`--additional-seconds` when needed. Admission rejects active, stale, retired or
incomplete predecessors. Background exit zero confirms acceptance only;
foreground exit codes follow `run`. Previous terminal evidence is preserved.

For an eligible packaged rejected candidate, with the service running:

```bash
uv run shipyard rework RUN_ID --feedback 'Handle the empty input case' --additional-seconds 600
```

For a published VERIFIED predecessor, first capture GitHub evidence with
`github-status`, then select IDs actually present in that saved observation:

```bash
uv run shipyard rework RUN_ID --observation /path/to/saved-observation.json --feedback-id REVIEW_ID --feedback-id COMMENT_ID --expected-attempt ATTEMPT_ID --additional-seconds 600
```

The observation must be in this Run's publication observation directory and
match its current verified candidate. Selected feedback becomes frozen PLAN
context; the remote PR head is never implicitly imported as the start revision.

## recover

Explicitly recover an eligible execution failure using fresh native invocations,
not session resumption. Eligible failure reasons are `EXECUTION_FAILED`,
`INVALID_STAGE_OUTPUT`, `CREDENTIAL_UNAVAILABLE` and `CREDENTIAL_REJECTED` on a
FAILED predecessor. Correct the underlying problem before recovery. Worker-loss
or incomplete captures require an explicit positive time grant.

```text
shipyard recover RUN_ID [OPTIONS]
```

| Argument / option | Type / default | Meaning and constraints |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Run with an eligible failed/interrupted latest Attempt. |
| `--additional-seconds N` | Integer ≥ 0; `0` | Explicit grant; must be positive for interrupted execution without complete PACKAGE evidence. |
| `--repo PATH` | Path; omitted | Saved-context constraint or legacy repository fallback. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Context lookup/storage root. |
| `--context PATH` | Path; omitted | Explicit saved context locator. |
| `--workspace PATH` | Path; omitted | Fresh isolated worktree, with `run` placement constraints and the later-Attempt default described under `rework`. |
| `--foreground` | Flag; false | Execute here instead of submitting to the service. |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Background service selector; unused in foreground. |
| `--json` | Flag; false | Background delivery JSON; foreground Run/Attempt and report/evidence paths. |
| `--expected-attempt UUID` | UUID; current latest Attempt | Reject a changed predecessor. |

Recovery discards partial checkout state. It starts at PLAN when validated durable
specification evidence exists, otherwise DESIGN. An inherited frozen spec survives
interrupted rework. The start SHA is the previous packaged candidate if available,
otherwise the previous Attempt's start SHA. Cumulative budgets, reserve protection,
stale-Attempt checks, preserved history and foreground/background result semantics
are the same as for rework. Interrupted spending is conservatively charged as the
entire prior allowance; it is not free retry time. Budget-exhaustion failures are
not in the eligible failure allowlist.

After resolving credentials or worker failure, for an eligible Run:

```bash
uv run shipyard recover RUN_ID --additional-seconds 900 --expected-attempt ATTEMPT_ID
```

## apply

Synchronously advance an eligible existing local branch to the latest Attempt's
packaged VERIFIED candidate. This validates exact-revision evidence and the
Run-owned candidate ref; it does not rerun agents, TEST or REVIEW.

```text
shipyard apply RUN_ID --branch BRANCH [OPTIONS]
```

| Argument / option | Type / default | Meaning |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Saved Run with a latest packaged VERIFIED candidate. |
| `--branch BRANCH` | String; **required** | Existing eligible local branch, not a new branch or remote ref. |
| `--repo PATH` | Path; omitted | Checkout constraint against saved context, or legacy fallback. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Saved context/evidence storage. |

The target must be an ancestor of the candidate (or already equal); an ahead or
divergent target requires a new Run. Advancement of a checked-out branch requires
a clean selected checkout, including ignored files. A target occupied by another
worktree blocks advancement. Unoccupied branches leave checkout files alone;
already-equal targets succeed as no-ops. Separate receipts live under
`RUNS_ROOT/applications/RUN_ID/`. Git and receipt persistence are not one
transaction: on partial failure inspect the reported target and preparation
records, resolve obstructions, then retry.

For a VERIFIED Run and an existing eligible local branch:

```bash
uv run shipyard apply RUN_ID --branch existing-local-branch
```

## runs

List saved Runs from `~/.shipyard/runs` plus service submissions, including custom
storage known through service delivery records. It does not discover arbitrary
custom roots, submit or resume Runs. Requires a running service; success means
history was read, not that listed Runs are VERIFIED.

```text
shipyard runs [OPTIONS]
```

| Option | Type / default | Meaning |
| --- | --- | --- |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Service selector. |
| `--json` | Flag; false | Print the service JSON response instead of human records. |

```bash
uv run shipyard runs --json
```

## status

Read a saved Run or service submission through the running service. Delivery
state, observed progress and validated Run outcome are separate. Exit zero means
the status read succeeded, not that verification passed.

```text
shipyard status RUN_ID [OPTIONS]
```

| Argument / option | Type / default | Meaning |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Saved/discoverable Run or service submission. |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Service selector. |
| `--json` | Flag; false | Print the service JSON record. |
| `--wait` / `--no-wait` | Boolean; false | Poll until terminal delivery or Run lifecycle; otherwise read once. |
| `--interval SECONDS` | Float from `0.01` to `60`; `1` | Polling interval when waiting. |

Leaving the viewer never cancels execution. Ctrl-C stops waiting with exit 130;
a service read error exits 1.

```bash
uv run shipyard status RUN_ID --wait --interval 2
```

## web

Serve the local browser workspace on loopback, with the service started separately.
The current workspace supports explicit Run and GitHub operations as well as
history, progress and evidence views; it is not limited to read-only monitoring.
Actions use the shared application/control boundaries and retain CLI approval and
verification rules. Closing the workspace does not stop Runs.

```text
shipyard web [OPTIONS]
```

| Option | Type / default | Meaning |
| --- | --- | --- |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Existing local service selector. |
| `--port PORT` | Integer `1`–`65535`; `8765` | HTTP port on `127.0.0.1`. |

With the service running, open the printed URL in a browser. Choose another port
if occupied. Restart an older service after upgrading to expose current endpoints.

```bash
uv run shipyard web --port 8765
```

## publish

Synchronously publish an explicitly approved, latest packaged VERIFIED candidate
to a dedicated GitHub branch `shipyard/RUN_ID` and PR. Requires authenticated `gh`
API access and working Git HTTPS push authentication/permission for the destination.
It runs outside the execution workflow, does not apply a local branch, and does
not rerun or extend Shipyard verification.

```text
shipyard publish RUN_ID --approve CANDIDATE_SHA --destination OWNER/REPO --base BRANCH [OPTIONS]
```

| Argument / option | Type / default | Meaning and constraints |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Live Run with validated packaged verification and its exact Run-owned Git candidate ref. |
| `--approve SHA` | String; **required** | Full VERIFIED candidate SHA, matched exactly under the Run lock. |
| `--destination OWNER/REPO` | String; **required** | GitHub owner/repository; fixed after first publication. |
| `--base BRANCH` | String; **required** | Existing destination branch; must differ from the dedicated Run branch and remain consistent on updates. |
| `--expect-head SHA` | String; omitted on first publication | Previously published full head SHA; required to match the prior publication on subsequent calls. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Saved context, verification and publication storage. |

Publication revalidates evidence/ref ownership under the Run lock. Initial push
requires the dedicated remote branch to be absent unless resuming a matching
prepared publication. Updates require the prior published commit to be an ancestor
of the new candidate; expected-head Git leases prevent overwriting external
changes. Existing PR identity, open state, branch, base and observed head must
agree. A closed/merged or externally changed PR is rejected.

Receipts and preparation records are kept under `RUNS_ROOT/publications/RUN_ID/`.
Matching retries can finish a prepared push/PR operation; a completed matching
publication returns its PR without a new workflow execution. Preserve the same
approval, destination, base and expected prior head on retry. Inspect partial
failure records rather than deleting or bypassing ownership checks. Later
publications append verification summaries to the PR conversation instead of
overwriting human-authored metadata. The command prints the PR URL.

After reviewing the exact candidate and authenticating, first publication:

```bash
uv run shipyard publish RUN_ID --approve CANDIDATE_SHA --destination owner/repo --base main
```

For a newly VERIFIED descendant Attempt of the same published Run:

```bash
uv run shipyard publish RUN_ID --approve CANDIDATE_SHA --destination owner/repo --base main --expect-head PREVIOUS_SHA
```

## github-status

Fetch a published PR's current head, checks, statuses, feedback and merge evidence
using authenticated `gh`, then persist a timestamped local observation. This is
an external GitHub read and local write, not a purely local inspection or a new
Shipyard verification. A remote head differing from the published verified
candidate is not verified by that candidate's evidence.

```text
shipyard github-status RUN_ID [OPTIONS]
```

| Argument / option | Type / default | Meaning |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Run with a completed GitHub publication. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Saved context and publication storage. |

Prints observation JSON to stdout and its saved path to stderr. Observations live
under `publications/RUN_ID/observations/`; a PR changing during capture is rejected
and can be explicitly retried. Use saved feedback IDs with `rework` when eligible.

```bash
uv run shipyard github-status RUN_ID
```

## cancel

Record a Run-level operator cancellation through the running local service.
A nonblank reason is required. The disposition blocks execution, continuation
and publication while preserving historical Attempt evidence and exact-SHA
verification. It does not delete data, close a published PR or undo a pushed head.

```text
shipyard cancel RUN_ID --reason TEXT [OPTIONS]
```

| Argument / option | Type / default | Meaning |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Saved Run to cancel. |
| `--reason TEXT` | String; **required** | Nonblank explanation, at most 1,000 characters. |
| `--runs-dir PATH` | Path; omitted | Explicit Runs root; otherwise service resolution of known/default storage. |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Running service selector. |

Pending delivery is cancelled. Active cancellation is cooperative at execution
checkpoints and bounded subprocess capture, rather than an immediate rollback;
execution finalizes retained evidence through PACKAGE. Recording the request does
not prove the active process has already stopped. Terminal evidence remains
historical. Repeating the same disposition/reason is idempotent; a conflicting
terminal disposition is rejected.

With the service running and a saved Run:

```bash
uv run shipyard cancel RUN_ID --reason 'Request withdrawn'
```

## supersede

Freeze a changed request as a separate Run, record supersession of the original,
and submit the replacement through the same serial local queue. Requires the
running service. Historical evidence is retained; original execution,
continuation and publication are blocked as with cancellation. Published GitHub
state is not automatically closed or reverted.

```text
shipyard supersede RUN_ID [SOURCE] --reason TEXT [OPTIONS]
shipyard supersede RUN_ID --replacement REPLACEMENT_RUN_ID --reason TEXT [OPTIONS]
```

| Argument / option | Type / default | Meaning and constraints |
| --- | --- | --- |
| `RUN_ID` | UUID; **required** | Original saved Run. |
| `SOURCE` | Optional string; omitted | Replacement source in either supported form; supply exactly one of this or `--replacement`. |
| `--reason TEXT` | String; **required** | Nonblank explanation, at most 1,000 characters. |
| `--replacement UUID` | UUID; omitted | Saved replacement capture, especially for retry; distinct from the original. |
| `--repo PATH` | Path; omitted | Original saved-context constraint or legacy fallback; source capture uses the resolved repository. |
| `--settings PATH` | Path; omitted | Replacement source capture only; default settings in resolved checkout. Unused with `--replacement`. |
| `--ref REF` | String; `HEAD` | Replacement source capture base; unused with `--replacement`. |
| `--runs-dir PATH` | Path; `~/.shipyard/runs` | Original context/storage root and replacement capture storage. |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Running service selector. |
| `--timeout SECONDS` | Integer ≥ 1; `1800` | New source capture budget; unused with `--replacement`. |
| `--verification-reserve SECONDS` | Integer ≥ 1; `300` | New source capture reserve, strictly less than timeout; unused with `--replacement`. |

A saved replacement must use the same Runs root, have valid saved context, and
initially be a fresh CREATED Run with no continuation, retirement or service
delivery. The service queues it using its own saved repository/context. Source
capture prints the replacement UUID before requesting supersession. If submission
fails after capture or disposition, retain that UUID and retry with
`--replacement` and the same reason; supplying a source again creates another
capture. Matching retries preserve the recorded link and avoid duplicate delivery.

For a changed readable request, with valid original context and a running service:

```bash
uv run shipyard supersede RUN_ID 'file:requests/revised request.md' --reason 'Requirements changed'
# If needed, retry using the replacement UUID printed above:
uv run shipyard supersede RUN_ID --replacement REPLACEMENT_RUN_ID --reason 'Requirements changed'
```

## service

Manage one local background service and its filesystem queue. The service wraps
the synchronous core and executes one Run at a time. Submission, observation and
service health are separate from validated Run lifecycle/outcome and exact-SHA
verification.

```text
shipyard service [--help] SUBCOMMAND [OPTIONS]
```

The group has only `--help`; `--control-dir` belongs after the subcommand. Each
of the four subcommands below accepts this option and `--help`, and no positional
arguments:

| Shared service option | Type / default | Meaning |
| --- | --- | --- |
| `--control-dir PATH` | Path; `~/.shipyard/control` | Control directory used for the Unix socket, queue, ownership and diagnostics. |
| `--help` | Flag; false | Show the selected subcommand's help and exit. |

### service serve

Run in the current process for supervisors or diagnostics; remains attached until
shutdown. SIGINT/SIGTERM request graceful drain of the active Run through PACKAGE.
Only one owner may serve a given control directory.

```text
shipyard service serve [--control-dir PATH] [--help]
```

In a dedicated terminal or supervisor, as an alternative to detached `start`:

```bash
uv run shipyard service serve --control-dir /path/to/control
```

### service start

Start detached and wait up to about ten seconds for readiness. If the selected
service is already healthy, print its health instead of starting another owner.
Diagnostics are appended to `CONTROL_DIR/service.log`; failure to become ready
reports that path. Agent execution uses the service process's environment.

```text
shipyard service start [--control-dir PATH] [--help]
```

```bash
uv run shipyard service start
```

### service status

Read and print service health as JSON. Requires the selected service to be
reachable. Success confirms the health request, not workflow success.

```text
shipyard service status [--control-dir PATH] [--help]
```

```bash
uv run shipyard service status
```

### service stop

Request graceful drain. The active Run continues through PACKAGE; this is not Run
cancellation or an immediate process kill. The command prints the service response
and can return before draining finishes. Requires a reachable service.

```text
shipyard service stop [--control-dir PATH] [--help]
```

```bash
uv run shipyard service stop
```
