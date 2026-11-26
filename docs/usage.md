# Run and deliver changes

Capture a request, inspect the Run's outcome, and deliver the exact Git commit
that Harborist verified. Start with the [quickstart](quickstart.md) if you have
not run Harborist before.

The examples below use the installed `harborist` command. From a development
checkout, prefix it with `uv run`. In the container deployment, use
`./deploy/harborist exec` in place of `harborist` and use paths inside the worker.
Replace `RUN_ID` with the UUID printed after capture or submission. See the [CLI reference](../COMMANDS.md) for all arguments,
defaults, and exit codes.

## Submit a Run

Start the [local service](background-control-plane.md). The target checkout
needs [mandatory checks and execution settings](configuration.md).

```bash
harborist service start
harborist run file:./request.md --repo /path/to/repository
```

For a GitHub issue, authenticate the GitHub CLI with access to the issue
repository. For a Docker deployment, sign in to the worker's bundled GitHub
CLI using the [Docker quickstart](quickstart.md#1-start-harborist).
Quote the source selector in shell commands.

```bash
harborist run 'github:owner/project#42' --repo /path/to/repository
```

`--repo` identifies the local repository Harborist will change. The issue may
come from a different repository. At capture, Harborist saves the request, base
commit, and settings. Later changes to the source or configuration take effect
on new Runs.

The command returns after durable queue admission. Use `harborist status RUN_ID
--wait` to follow execution. If a request was captured but submission failed,
correct the error and submit the printed Run UUID.

## Capture a Run

Use `intake` to review the frozen inputs before any agents or checks run.

```bash
harborist intake file:./request.md --repo /path/to/repository
harborist inspect RUN_ID
harborist methodology RUN_ID --stage build
harborist run RUN_ID
```

`inspect` prints the saved contract as JSON. `methodology` shows the playbook
and skills included in the capture. Use `--stage design`, `plan`, `build`, or
`review` to see the guidance for a particular agent stage.

Pass capture options such as `--ref`, `--settings`, and `--timeout` with the source
or `intake`. Submitting a saved UUID uses the Run's frozen inputs. If the capture
uses a custom path, see [saved context and workspace placement](storage-and-recovery.md).

## Inspect results and evidence

```bash
harborist runs
harborist status RUN_ID --wait
harborist status RUN_ID --json
```

The browser workspace shows the same Run history and lets you open stage
evidence and earlier Attempts. Start it with `harborist web` and open
[http://127.0.0.1:8765](http://127.0.0.1:8765).

| Where to look | What it tells you |
| --- | --- |
| Service delivery state | Whether the service queued, finished, failed, or lost the execution. |
| Run outcome | Whether the candidate was verified, failed checks, needs changes, or reached another recorded outcome. |
| `report.md` | A human-readable summary of the exact candidate, checks, and review. |
| `evidence.json` | The machine-readable index and hashes for packaged evidence. |

A `FINISHED` delivery may contain a software failure. For automation, read
`run.outcome` and `run.failure_reason` from `status --json`. A successful
`status --wait` indicates a successful read. For evidence paths and integrity
rules, see [Storage and recovery](storage-and-recovery.md).

## Run in the foreground

Use `--foreground` for synchronous execution and terminal exit codes. This
mode can run without an active service.

```bash
harborist run file:./request.md --foreground
harborist run RUN_ID --foreground --json >result.json 2>progress.log
```

These commands illustrate two separate Runs. Use the second form for a
previously captured Run that is still `CREATED`.

Progress goes to stderr. With `--json`, stdout contains the terminal result
with the `run`, `workspace`, `report`, and `evidence` fields. The exit codes
are `0` for `VERIFIED`, `2` for other completed software outcomes, `1` for
execution or finalization errors, and `130` for cancellation. If interruption
prevents packaging, the command can exit `1`.

## Apply a verified candidate

`VERIFIED` establishes the exact candidate revision; it does not update your
source checkout or any branch. After PACKAGE, the terminal prints “Verified;
awaiting application” with a shell-quoted command. Replace
`REPLACE_WITH_LOCAL_BRANCH` with an existing local branch:

```bash
harborist apply <run-id> --branch main
harborist apply <run-id> --branch release --repo '/path/to/repository' --runs-dir '/path/to/custom runs'
```

Application is a separate synchronous user operation. It does not invoke agents,
rerun verification, create commits, or push. Saved execution context selects the
original repository independently of cwd. Custom storage requires `--runs-dir`;
the default is `~/.harborist/runs`. Explicit repository/storage options must match
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
Git ref updates check the expected old SHA. Avoid concurrent changes to
the checkout while applying a candidate.

## Rework and recovery

Rework a TEST_FAILED or CHANGES_REQUIRED result with a fresh Attempt in the same Run:

```bash
harborist rework <run-id> --feedback 'Fix the failing AC-002 behavior'
harborist status <run-id> --wait
```

Recover an eligible infrastructure/output failure:

```bash
harborist recover <run-id>
```

Both commands queue through the local service by default. Add `--foreground` to
execute synchronously, and `--json` for machine-readable results. They use the same
saved context and `--repo`, `--runs-dir`, `--context` and fresh `--workspace` options
as execution. `--expected-attempt <attempt-uuid>` rejects a stale predecessor;
without it the CLI captures the currently selected Attempt identity. Background
exit zero means acceptance. Foreground exits are 0 for VERIFIED, 2 for other
software outcomes, 1 for failure and 130 for operator cancellation.

Recovery accepts EXECUTION_FAILED, INVALID_STAGE_OUTPUT, CREDENTIAL_UNAVAILABLE
and CREDENTIAL_REJECTED. Configuration errors, internal errors, exhausted-budget
failures, CANCELLED, VERIFIED, clarification and rescoping outcomes require a new
Run. Neither command resumes a native agent session. Recovery discards partial
checkout work; it uses the previous packaged candidate when available, otherwise
the failed Attempt's start SHA. Rework always starts at the previous candidate.
A ready durable spec is reused; PLAN and BUILD run afresh, followed by fresh
mandatory TEST and independent REVIEW for the exact new candidate. Failed TEST
still prevents REVIEW. Feedback cannot rewrite the spec; a material acceptance
change produces NEEDS_RESCOPING and requires a new Run.

All Attempts share the frozen Run budget and verification reserve. Time already
spent is subtracted. Add `--additional-seconds 600` only when explicitly granting
more time. Worker loss or missing PACKAGE/timing requires a grant and
conservatively charges the entire previous allowance, so the grant must exceed
the frozen verification reserve. For example:

```bash
harborist recover <run-id> --additional-seconds 600
```

The service never automatically retries an INTERRUPTED claim. Stop the old
executor before recovery; the Run lock rejects an active parent executor.
Incomplete admissions, corrupt journals, missing Attempt identity or invalid
upstream captures fail closed and require inspection/new intake rather than
in-place repair. A preflight error before Attempt creation leaves the predecessor
unchanged. Failures after reservation retain the new directory and are never
silently rolled back.

Reports and normal status refer to the latest Attempt. Prior evidence stays at
its original paths; subsequent captures are under
`<runs-root>/<run-id>/attempts/000001`, `000002`, and so on. Later default checkouts
are `<runs-root-parent>/workspaces/<run-id>/<attempt-id>`; use `--workspace` for
custom placement. The original execution-context locator stays at the Run root.
`harborist apply` validates and applies only the latest VERIFIED candidate.
Rework/recovery does not publish to GitHub or apply code automatically.

## Publish a verified candidate to GitHub

Use authenticated GitHub CLI for PR operations and a Git credential for HTTPS
pushes. The Docker worker uses its GitHub CLI login for both. Supply the exact
candidate SHA printed by Harborist, the destination
repository, and an existing PR base branch.

```sh
harborist publish RUN_ID --approve CANDIDATE_SHA --destination OWNER/REPO --base main
harborist github-status RUN_ID
```

For a later verified Attempt, add `--expect-head PREVIOUSLY_PUBLISHED_SHA`.
Harborist uses a dedicated branch for the Run and checks that the previous head
is still current and is an ancestor of the approved candidate. If a push or PR
creation fails midway, retry with the same arguments. Publication records and
observations live under `publications/RUN_ID/` in Runs storage.

`github-status` saves a dated snapshot and shows its path. CI and merge evidence
come from GitHub and remain separate from the original TEST and REVIEW. To act
on specific feedback, pass that path and one or more feedback IDs from the
snapshot.

```sh
harborist rework RUN_ID --observation SNAPSHOT_PATH --feedback-id review:123
```

The new Attempt starts from the local verified candidate, uses the frozen spec,
and runs fresh TEST and REVIEW. Commits added by humans to the PR branch are
never imported implicitly.

## Cancel or replace a Run

```sh
harborist cancel RUN_ID --reason "Request withdrawn"
harborist supersede RUN_ID file:./updated-request.md --reason "Requirements changed"
```

Both commands use the local service. Active execution stops at a cancellation
checkpoint, including while native tools and checks are running. The original
Run's packaged artifacts stay available, and its unpublished candidates
become ineligible for GitHub publication. Existing pull requests remain
available for human handling.

Supersession captures and queues a new Run. Status on the original shows the
replacement ID. If the service request fails after capture, retry with
`harborist supersede RUN_ID --replacement REPLACEMENT_ID --reason "Requirements changed"`.

## Set up local Codex

In **Integrations → Codex**, select **Check Codex** to check the CLI and login
used by the background service. Sign in with `codex login` in a terminal if
credentials are unavailable. After installing the CLI or changing environment
variables used by the service, restart the service from that environment.
Harborist discards the login command's output and displays a diagnostic message.
The check uses local login status. A Run exercises access to the chosen model.

Under **Execution profile**, select a saved Workspace and choose **Edit profile**
to set the model and reasoning effort in its selected execution settings YAML.
The file must already exist. Saving rewrites its formatting and removes YAML comments.
Intake freezes the selected profile for each new Run. Rework and recovery use
the profile already frozen for their Run.

From a terminal, the equivalent commands use the terminal's Codex environment
and the selected checkout's settings:

```sh
harborist agent check --repo /path/to/checkout
harborist agent configure --repo /path/to/checkout --model gpt-6.1-sol --effort high
```

Use `--settings PATH` to select an explicit settings file. Omit `--effort` in
`configure` to use Codex's default. Use `agent check --json` for separate
connection and profile statuses. The check exits with status 1 if either needs
attention.

## Queue a Run from the GitHub ticket Inbox

Open **Ticket Inbox** in the browser workspace. Enter the source GitHub repository
as `owner/repo` and select **Load issues**. The local service uses its authenticated
GitHub CLI to fetch up to 100 open issues. **Refresh issues** performs another
fetch. Select an issue and a saved target Workspace, review both selections,
then select **Queue Run**. The target Workspace determines the checkout, settings,
base ref, and execution budget. Its GitHub origin can differ from the issue's
repository.

Use the same service commands from the CLI:

```bash
harborist tickets list owner/source
harborist tickets refresh owner/source
harborist tickets queue 'owner/source#42' --workspace WORKSPACE_ID
```

Find the saved Workspace UUID on the **Workspaces** page. Each command accepts
`--control-dir` for a nondefault service directory. List and refresh both fetch
from GitHub. If a queue response is uncertain, repeat the same command with
`--request-id UUID` using the request ID printed on failure.

The service fetches the issue again at intake and saves the resulting title,
body, labels, and issue link before queue admission. Later edits do not change
that Run. The browser Run detail links to the source ticket, and
`harborist inspect RUN_ID` shows its saved identity and URL.
