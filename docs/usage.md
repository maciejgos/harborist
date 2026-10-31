# Background execution (Phase 10)

Start `shipyard service start` before using `shipyard run`. Runs now submit to
the service and return promptly. Use `shipyard status <run-id> --wait` to view
the result. Add `--foreground` to run examples below when synchronous output or
terminal exit codes are needed. See the [service guide](background-control-plane.md)
for migration, JSON response semantics and interruption behavior.

# Usage

[Documentation index](README.md) · [Architecture](../ARCHITECTURE.md)

## Available commands

From the development checkout, prefix commands with `uv run` (for example,
`uv run shipyard --help`). An installed `shipyard` entry point and
`uv run python -m shipyard` expose the same CLI.

| Command | Purpose |
| --- | --- |
| `shipyard intake <source>` | Capture a CREATED Run with frozen inputs, then print its summary and execution command without running agents or checks. |
| `shipyard run <source>` | Capture a source and execute the delivery workflow synchronously. |
| `shipyard run <run-id>` | Execute a previously captured CREATED Run using its frozen inputs. |
| `shipyard inspect <run-id>` | Validate and print the saved contract as JSON without rereading the original inputs. |
| `shipyard apply <run-id> --branch <branch>` | Apply a packaged VERIFIED candidate to an existing local branch. |
| `shipyard methodology <run-id>` | Preview the frozen playbook and skills as JSON without executing or modifying the Run. |

`<source>` accepts `file:path/to/issue.md` or `github:owner/repo#42` (quote
GitHub selectors in shell commands). `<run-id>` is the captured Run's UUID.

Available options:

| Applies to | Options |
| --- | --- |
| All commands | `--runs-dir PATH` selects Run storage (default: `~/.shipyard/runs`); `--help` shows command usage. |
| `intake` and `run <source>` | `--repo PATH` selects the target repository (default: current directory); `--settings PATH` overrides the target root's `shipyard.settings.yaml`; `--ref TEXT` selects the base commit-ish (default: `HEAD`); `--timeout INTEGER` sets the total budget (default: 1800 seconds); `--verification-reserve INTEGER` reserves verification time (default: 300 seconds). The total budget must exceed the reserve. |
| `intake` | `--json` prints the full frozen contract instead of the human-readable summary. |
| Both `run` forms | `--workspace PATH` selects a fresh isolated workspace; `--json` prints the full Run result instead of the human-readable summary. |
| `run <run-id>` | `--context PATH` selects an explicit saved context locator; `--repo PATH` constrains the saved repository. `--runs-dir` must also match saved context when present. Source-capture options cannot override frozen inputs. |
| `apply` | `--branch TEXT` is required; `--repo PATH` constrains the saved repository. |
| `methodology` | `--stage STAGE` previews composed guidance for one native-agent stage: `design`, `plan`, `build`, or `review`. |

Use `shipyard --help` for the command list, or `shipyard <command> --help`
for full usage. The top-level `--install-completion` and `--show-completion`
options install or display shell completion.

## Capture a Run

Run repository examples from the repository root.

The target repository must have a committed root `shipyard.yaml` with its mandatory
checks. Shipyard includes its own verification and execution configuration.
Intake defaults to `shipyard.settings.yaml` at the resolved target checkout root.
This checkout supplies an explicit model/profile and canonical playbook/skill
sources; intake freezes these inputs without invoking the selected model.

```bash
uv run shipyard intake 'github:maciejgos/shipyard#7'

uv run shipyard intake file:examples/intake/issue.md

# Existing explicit invocations remain supported.
uv run shipyard intake file:examples/intake/issue.md \
  --repo . --settings examples/intake/settings.yaml

uv run shipyard intake 'github:owner/repo#42' \
  --repo /path/to/target --settings /path/to/operator.yaml

uv run shipyard inspect RUN_UUID
uv run shipyard methodology RUN_UUID
uv run shipyard methodology RUN_UUID --stage build
```

Intake first validates methodology metadata, then prints a concise human-readable
summary with the Run ID, repository, base revision, task reference, CREATED status,
and a copyable execution command. Use `--json` for the full frozen contract on
stdout. Existing scripts consuming the former default JSON must add `--json`.
Saved contracts and existing captures require no migration. Intake does not
execute agents or checks. Inspect validates the saved capture without consulting
original inputs. `methodology` previews the frozen playbook and skills as JSON;
`--stage` selects composed guidance for an agent stage. All commands accept
`--runs-dir`; intake also accepts `--ref`,
`--timeout` and `--verification-reserve`. Defaults are HEAD, 1800 seconds overall,
300 seconds reserved, and `~/.shipyard/runs`. A shorter timeout must still exceed
the reserve; override both when needed. Expected failures return nonzero status.
`uv run python -m shipyard --help` provides the same commands. See the
[CLI specification](../spec/017-intake-cli/spec.md).

## Saved methodology preview

`shipyard methodology RUN_UUID` loads the saved capture and prints compiled
playbook/skill metadata, guidance and exact content identities. Add `--stage build`
(or design/plan/review) for composed guidance. It never reads current methodology
files, executes stages or changes the saved contract. `inspect` remains available
for historical plain Markdown captures; `methodology` returns a compilation error
for those captures. See [preview specification](../spec/025-methodology-preview/spec.md).

## Synchronous execution and PACKAGE

New captures using the example settings adopt engineering guidance v2. BUILD can
return a bounded `process_report` with red/green command records and limitations.
Shipyard saves it as `build/build-process.json`, supplies it to REVIEW, and indexes
it in PACKAGE independently of diagnostic truncation. These records are explicitly
agent-reported: they cannot override trusted TEST or prove historical execution
order. Routine TDD policy stays in operating guidance; explicitly requested proof
still requires adequate evidence. Older captures/responses remain readable.
See the [process-evidence contract](../spec/046-build-process-evidence/spec.md).

Capture and execute synchronously in one command:

```bash
shipyard run 'github:maciejgos/shipyard#7'
shipyard run file:./issue.md
# From a development checkout:
uv run shipyard run 'github:maciejgos/shipyard#7'
uv run shipyard run file:./issue.md
```

Source mode calls intake once, saves one CREATED Run and executes that same
capture through DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE. Files are read
once and GitHub issues fetched once; execution uses the saved snapshot. The issue's
GitHub repository is independent of the target selected by `--repo`. GitHub capture
uses local `gh`; failures explain installation/PATH, authentication/access,
timeout retry, or invalid-response corrections without exposing response bodies.

Source mode accepts `--settings`, `--ref` (default HEAD), `--timeout` (1800 seconds),
and `--verification-reserve` (300 seconds) with their intake meanings. Settings
default to `shipyard.settings.yaml` at the resolved target checkout root, including
from a subdirectory. Explicit `--settings PATH` takes precedence, resolving relative
to the invocation directory; unavailable or invalid selected settings never fall
back. Capture freezes settings, methodology, base revision and budget.

UUID mode executes the saved Run without recapturing or reloading live settings.
Explicit capture-only options are rejected even when their value equals the
default; omit them to execute a saved Run, or supply a source to create a new one.
`--context` selects an existing Run only and cannot accompany a source.
Both modes accept `--repo`, `--runs-dir`, `--workspace` and `--json`, preserving
saved-context constraints and workspace placement rules in [storage and recovery](storage-and-recovery.md). Invalid
selectors and conflicting options fail before capture or agent execution.

Capture notices and progress go to stderr. Human mode ends with the terminal
summary and report/evidence locations. `--json` writes one terminal execution-result
document to stdout (`run`, `workspace`, `report`, `evidence`), never an intake
contract. Capture/preflight failures leave stdout empty. Capture failure starts no
agents and creates no valid Run; once admitted, failures/cancellation retain the
ordinary terminal evidence and exit statuses, without retry or recapture.
Verification does not apply a candidate, push changes, or close an issue.

If capture succeeds but execution preflight fails, stderr identifies the retained
CREATED UUID and prints a shell-quoted recovery command. Correct the problem and
execute that UUID rather than capturing again. Custom storage needs its locator;
workspace placement errors need a fresh external path, for example:

```bash
shipyard run <run-id> --runs-dir '/absolute/custom runs' --workspace '/absolute/fresh external workspace'
uv run shipyard run <run-id> --runs-dir '/absolute/custom runs' --workspace '/absolute/fresh external workspace'
```

The original source and live settings are unnecessary for recovery; saved context
selects the target repository. No automatic restart occurs after admission, and
terminal Runs remain immutable.

For capture-only use, keep `intake`, then copy its execution command when ready:

```bash
shipyard intake file:./issue.md --repo /path/to/repository
# stdout: a human-readable summary including a command such as:
shipyard run <run-id>
```

To capture the full frozen contract as JSON instead (the command hint remains on
stderr):

```bash
shipyard intake file:./issue.md --settings ./operator.yaml --repo /path/to/repository --json > contract.json
```

See [storage and recovery](storage-and-recovery.md) for context locators,
workspace placement, custom storage and legacy captures.

## Results, evidence and progress

The target repository must contain the frozen base commit. Codex must
already be installed and authenticated locally. Each native stage starts a fresh
process. Execution stays local and synchronous; Ctrl-C cancels the active executor
best-effort and packages a CANCELLED result. Exit codes are 0 for VERIFIED, 2 for
other completed software outcomes, 1 for execution or packaging failure, and 130
for cancellation (an interruption during packaging exits 1). By default the command
prints a concise human-readable summary: Run ID, lifecycle, software outcome or
failure reason, exact candidate SHA, mandatory-check and acceptance-review counts,
and absolute report/evidence paths. Unavailable work is identified explicitly.
Verification does not apply the candidate to the target branch.

```bash
shipyard run <run-id>
shipyard run <run-id> --json
```

Scripts consuming the previous default JSON stdout must add `--json`. This option
prints one complete JSON document with the existing four fields: `run` (including
nested verification when present), `workspace` (absolute string or null), `report`,
and `evidence` (absolute artifact paths). Both modes execute the same workflow,
persist the same evidence, and use the same exit codes. Full check and criterion
records remain in saved artifacts. `inspect` continues to return the frozen
contract after execution.

The application entry point is `shipyard.application.execution.execute_run`, with
explicit `FileRunStore`, Run ID, `GitRepository` and `NativeAgent` parameters,
plus an optional fresh workspace path. Existing individual stage APIs remain
available for lower-level use.

The frozen total budget starts at execution admission. DESIGN, PLAN and BUILD
share the allowance before the verification reserve; TEST and REVIEW share the
remaining total. Unused time rolls forward. Monotonic time controls deadlines;
UTC timestamps, measured durations and remaining budget are recorded for the Run
and stages. Native-agent deadlines use whole seconds, so less than one remaining
second cannot admit another agent. PACKAGE records its own timing outside that
allowance and remains available when remaining execution time is zero.

New CLI captures also contain a create-only `execution-context.json` locator.
Run directories contain `run.json`, `contract.json`, `intent.*`, `attempt.json`,
`events.jsonl`, timing records, stage directories, `report.md`, and `evidence.json`.
DESIGN/PLAN/BUILD/REVIEW hold structured results, artifacts and bounded diagnostics;
TEST holds its complete check manifest and numbered logs. `invocation.json` records
log truncation and optional usage, including for provider process failure/timeout.
Partial captures lack their success manifest. `evidence.json` is published last and
indexes all prior files, including the report, by relative path, length and SHA-256.
It does not hash itself or the retained workspace subtree. Symlinks outside the
workspace, including a replaced workspace root, are rejected.

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

See the [Phase 8 acceptance audit](../spec/045-phase8-acceptance-audit/report.md).

During `shipyard run`, progress appears automatically on stderr: the requested
Run ID, stage starts, measured completion durations, failures, cancellations and
skipped stages. Active stages print an elapsed-time line every 15 seconds,
including while agent calls, trusted checks or packaging block. These lines mean
only that execution is awaiting completion; they do not establish semantic
progress or agent/tool health. Durations use a monotonic clock.

After packaging, stderr shows the terminal result and absolute report/evidence
paths. Stdout contains the terminal summary by default; scripts select `--json`
for a single JSON document. Progress stays on stderr in either mode. Plain lines
are flushed immediately and remain readable in redirected logs, for example:

```bash
shipyard run <run-id> --context /absolute/execution-context.json --json \
  >result.json 2>progress.log
```

### Apply a verified candidate

`VERIFIED` establishes the exact candidate revision; it does not update your
source checkout or any branch. After PACKAGE, the terminal prints “Verified;
awaiting application” with a shell-quoted command. Replace
`REPLACE_WITH_LOCAL_BRANCH` with an existing local branch:

```bash
shipyard apply <run-id> --branch main
shipyard apply <run-id> --branch release --repo '/path/to/repository' --runs-dir '/path/to/custom runs'
```

Application is a separate synchronous user operation. It does not invoke agents,
rerun verification, create commits, or push. Saved execution context selects the
original repository independently of cwd. Custom storage requires `--runs-dir`;
the default is `~/.shipyard/runs`. Explicit repository/storage options must match
the saved context after resolving aliases and repository subdirectories. Invalid
existing context fails closed. Only absent context permits legacy `--repo`/cwd
and default storage resolution.

Only a complete packaged COMPLETED/VERIFIED Run with consistent immutable
DESIGN, TEST and independent REVIEW evidence can be applied. The original base
and candidate commit and Run-owned candidate ref must remain available. Mutable
retained workspace edits are never applied. Targets must be existing local
branches and strictly behind the exact candidate; ahead or divergent branches
require a new Run against the updated target.

For a target checked out in the selected checkout, advancement requires a clean
index and working tree, including no untracked or ignored files, and no pending
Git operation. Preserve changes elsewhere and finish or abort Git operations
before retrying. A target occupied by another worktree is refused: free that
branch first. An unoccupied branch advances without switching or changing the
selected checkout, even if that checkout is dirty. Hooks are disabled; application
never resets, cleans, stashes, or discards user files. An already-equal target
reports **Already applied**, without touching checkout files; this does not assert
that those files are clean.

Success prints the Run, branch, candidate and durable receipt path. Receipts are
stored separately at `<runs-root>/applications/<run-id>/<target-key>.json`, keyed
by normalized repository and full branch name. They record the previous/resulting
SHAs and a timezone-qualified timestamp. Different targets get separate receipts;
repetition reuses the existing receipt. An observed no-op without an earlier
receipt records both SHAs as the candidate. Terminal Run artifacts and verification
evidence remain unchanged.

Receipt preparation happens before advancement. Partial failures return nonzero,
report the observed target SHA and receipt/preparation paths, and preserve state.
Inspect those paths and the checkout, resolve the obstruction, then retry the same
command. Retry revalidates evidence, recognizes an already-equal target and can
finish a missing receipt without advancing again. Pending and confirmation files
remain as recovery evidence. Without a durable post-advancement confirmation,
retry records only the observed no-op, not an assumed historical advancement.
Git ref updates check the expected old SHA; no rollback is attempted. There is no
cross-resource transaction or power-loss guarantee, and concurrent external
checkout/file writers remain outside the local PoC guarantees.
