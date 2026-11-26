# Rust foreground workflow and verification

This branch ports Harborist's trusted-local verification and local Markdown
foreground workflow to a standalone Rust executable for Linux. It reads version 1 checks from
`harborist.yaml` at a supplied base commit, checks out an exact candidate in a detached Git
worktree, runs every check in order, and emits JSON and bounded log files.
The experiment uses fresh local Git repositories inside Docker and runs with
container networking disabled. It expects trusted check commands.

## Run a Rust foreground task

The Docker build used by the comparison produces the release executable in
`target/release/harborist-verify` under this directory. In a Linux container with
Git and an authenticated Codex CLI on PATH, run:

```sh
harborist-verify run REPO BASE_SHA SOURCE NEW_RUN_DIR
```

Use an exact base commit and a fresh Run directory outside the source checkout.
For SOURCE, use a Markdown path, `github:OWNER/REPO#NUMBER`, or a GitHub Issue
URL. GitHub capture requires an authenticated `gh` CLI in the container.
The checkout must have Git author identity configured. The runner freezes the
Markdown intent and base revision's verification config, then invokes fresh
Codex processes for DESIGN, PLAN, BUILD, and REVIEW. It commits BUILD in a
detached worktree, runs trusted checks, and opens a clean worktree for REVIEW.
A check failure or tracked checkout change prevents REVIEW. PACKAGE writes
`report.md` and `evidence.json` under the Run directory. The Run's candidate ref
keeps the candidate reachable after worktree cleanup.

With `harborist.settings.yaml` in the checkout or an explicit
`--settings FILE` argument, intake captures the trusted-local policy, Codex
model and arguments, playbook, and skills. Saved Runs use the captured
settings and asset content. Docker Sandboxes policies require the Python
runtime. When there is no settings file, the Rust adapter uses the installed
Codex CLI's default model. The Docker suite supplies a deterministic Codex
fixture and makes no external model calls.

## Save a Run and execute it later

```sh
harborist-verify intake REPO BASE_SHA SOURCE NEW_RUN_DIR
harborist-verify execute RUN_DIR
```

Intake prints the Run UUID and saves the captured intent, verification config,
and their digests. It has no Codex dependency. Execution checks the saved digests
and uses the recorded base commit. Changes to the original Markdown or to
the repository's current HEAD do not change the Run. Only one caller can
admit a fresh Run. The original execution records stay available if execution
fails or is interrupted.

## Run the local worker

In a Linux container with Git and Codex on PATH, start the worker and leave it
running. Use the same container-visible checkout, Run directory, and control
paths for the worker and client commands.

```sh
harborist-verify worker CONTROL_DIR
```

From another shell, submit a saved Run and check delivery using the UUID
printed by intake.

```sh
harborist-verify submit CONTROL_DIR RUN_DIR
harborist-verify delivery CONTROL_DIR RUN_UUID
```

One worker owns each control directory and executes one delivery at a time.
Submitting the same saved Run twice returns the same delivery. A restarted
worker marks previously running deliveries as interrupted and leaves their
records available. Use `worker CONTROL_DIR --once` to process at most one
queued delivery and exit. The `finished` delivery state means PACKAGE wrote
terminal evidence. Read `evidence.json` for the Run outcome.

## Read Runs from the control socket and browser

Run these commands alongside the worker in a container that shares the
control directory and the same Run paths:

```sh
harborist-verify service CONTROL_DIR
harborist-verify web CONTROL_DIR 8765
```

The control service serves health, queued Run summaries, and named terminal
artifacts over `CONTROL_DIR/service.sock`. Its GET responses are accessible
through Harborist's existing Unix-socket client. The loopback browser serves
the existing workspace assets and forwards allowlisted GETs through that
socket. The monitor supports the Run list, Run detail, and named report, specification, test log, and
evidence reads for the selected Attempt. The Workspaces page saves checkout defaults. New Run accepts Markdown and
GitHub Issue sources. Tickets lists open issues and queues a selected issue to
a saved Workspace. Start the worker to execute queued Runs. GitHub transport
is tested using an offline `gh` fixture.

Use the Docker checks when validating the port without performance timing:

```sh
./experiments/rust-verification/docker-check.sh
```

## Apply a verified candidate

```sh
harborist-verify apply RUN_DIR BRANCH
```

Application requires a packaged VERIFIED Run with matching specification,
TEST, and REVIEW digests. The command verifies the Run-owned candidate ref
and fast-forwards an existing local branch using the expected old SHA.
The recorded checkout must be clean when it has the target checked out.
Application refuses a branch checked out in another worktree. The Run's
terminal evidence stays intact and a separate receipt records the application.
Older Rust evidence without verification digests requires a fresh Run before
application.

## Publish a verified candidate to GitHub

```sh
harborist-verify publish RUN_DIR APPROVED_SHA OWNER/REPO BASE_BRANCH
```

Use the full candidate SHA from packaged verification and an existing GitHub
base branch. The command uses authenticated Git and `gh` in the container. It
pushes the approved commit to a dedicated Run branch and prints the pull
request URL. Retrying the same publication checks the prepared record and
remote head before reusing the existing pull request. For a later verified
Attempt, append `--expect-head PREVIOUS_PUBLISHED_SHA`.
Harborist advances the existing PR branch only if its head matches the expected
SHA and the new commit descends from it. The update adds a verification comment
to the existing PR. You can also approve it from GitHub delivery in the
browser for a queued Run that finished verification. The browser displays the
published commit and pull request from the local receipt. The Docker test uses
a local Git remote and an offline `gh` fixture.

## Refresh GitHub PR evidence

Use **Refresh PR evidence** in the workspace or run:

```sh
harborist-verify github-status RUN_DIR
```

An observation records the PR head, merge status, checks, commit statuses,
and review feedback for the published Run. Harborist checks the PR again
before saving the observation and rejects it if the PR changed during
capture. The browser shows the latest saved observation. Select feedback entries to
queue rework against the locally verified candidate. The selection is bound
to the saved observation and that candidate. A changed remote PR head stays
in the observation and is never imported as the starting revision.

## Cancel a Run

Use **Cancel Run** in the workspace or run the following command in a
container that sees the saved Run directory:

```sh
harborist-verify cancel RUN_DIR "Operator stopped this Run"
```

A queued Run is skipped. For an active Run, the worker stops the current
Codex or TEST process group and records the cancelled stage in terminal
evidence. Cancellation preserves existing artifacts and prevents further
execution, candidate application, and GitHub publication. The operator
reason stays in the saved retirement record.

## Supersede a Run

Use **Supersede Run** in the workspace to capture a replacement request and
queue it under its own Run ID. Harborist saves the replacement before retiring
the original Run. The original keeps its evidence and links to the replacement
in its retirement record. A retry with the same request inputs reuses the
replacement Run and its queue delivery.

## Rework a failed candidate

For a Run with `TEST_FAILED` or `CHANGES_REQUIRED`, use the Attempt UUID
shown in its evidence:

```sh
harborist-verify rework RUN_DIR EXPECTED_ATTEMPT "Address the failing check"
```

Rework starts a new Attempt from the previous candidate and uses the
recorded specification without repeating DESIGN. It sends prior PLAN,
TEST, and REVIEW evidence plus the operator's feedback to PLAN. The
candidate gets fresh TEST and REVIEW results. The earlier Attempt's
artifacts and Git ref are preserved. Supply an optional final argument
in seconds to increase the remaining budget.

The CLI command runs in the foreground. **Rework Run** in the browser queues
the request for the worker, which checks the expected predecessor again
before starting. The Run summary defaults to the latest Attempt, and the
Attempt selector opens historical evidence. Candidate application uses the
latest Attempt’s verification and Git ref.

## Recover a failed execution

Use **Recover Run** in the browser for an eligible execution or stage-output
failure, or run:

```sh
harborist-verify recover RUN_DIR EXPECTED_ATTEMPT "Retry the failed stage"
```

Recovery creates a new Attempt and preserves the failure evidence. If the
previous Attempt recorded a valid specification, recovery checks its digest
and starts at PLAN. Otherwise it starts with a fresh DESIGN invocation.
An optional final argument grants additional seconds. After an abrupt worker
stop, restart the worker to record the interruption. Explicit recovery then
requires a grant large enough to cover the verification reserve and the new
Attempt. A completed DESIGN checkpoint lets recovery keep the specification.
The interrupted Attempt stays available and its partial checkout is never
used as the starting revision.

## Use legacy verification configuration

For a repository that still commits `shipyard.yaml`, Rust intake reads
those checks at the selected base commit when `harborist.yaml` is absent.
A present primary configuration must be readable and valid.
The frozen copy in the Run directory is always named `harborist.yaml`.

## Inspect Runs saved by Python Harborist

Start the Rust control service with the existing Runs directory visible inside
the container:

```sh
harborist-verify service CONTROL_DIR --runs-dir EXISTING_RUNS_DIR
```

The service includes saved Python Runs in browser history and reads their
Attempt summaries, reports, specifications, and packaged evidence in place.
It checks the lifecycle journal and verifies attribution before displaying a
verified commit. It leaves the saved files untouched.

To transfer an unstarted trusted-local Run, stop the Python executor for
that Run, then use a fresh directory for the Rust copy:

```sh
harborist-verify import-python PYTHON_RUN_DIR NEW_RUST_RUN_DIR
harborist-verify execute NEW_RUST_RUN_DIR
```

The import keeps the Run UUID, intent, exact base, verification checks,
budget, and captured methodology and profile. It verifies the saved Git
context and checks the verification bytes at the frozen base revision.
The original remains inspectable in Python format. Already-started
Python Runs are not eligible for this import.

For an already verified Python Run, the Rust `apply RUN_DIR BRANCH`
command can apply the recorded candidate directly. It checks the PACKAGE
file digests, passing TEST capture, exact REVIEW inputs, and the original
Run-owned Git ref. Rust stores the application receipt outside the Python
Run directory so the original PACKAGE index stays valid.

The Rust `publish` command also accepts a verified Python Run directory for
its first GitHub publication. It validates the same historical evidence and
writes publication records beside the Python Runs directory. If the Run
already has a Python publication receipt, keep using that publication path.

## Run the comparison

From the repository root with Docker running:

```sh
./experiments/rust-verification/docker-exercise.sh
```

The script builds the existing Harborist Python runtime and compiles the Rust
binary in a separate build container. The parity check and both timed commands
then run in the same Linux container, with a two-CPU limit. There are no model
calls, external repositories, or host mounts with write access during timing.

Each verification-only trial starts a fresh process, reads and hashes the frozen config, creates a
worktree, runs three short shell checks on the same candidate commit, writes and
serializes the results, and removes the worktree. The Python adapter calls the
existing Harborist parser and check runner. The timing includes Git, shell,
and language startup. Both commands run in alternating order, with three
warmups per implementation and 60 measured trials per implementation by
default. The comparison checks parsed evidence and log bytes on every trial.
It also checks failure, timeout, output truncation, strict YAML field types,
saved Run admission, and worker restart behavior outside the timed workloads.

The Rust executable accepts these positional arguments:

```text
harborist-verify REPO BASE_SHA CANDIDATE_SHA NEW_CHECKOUT NEW_LOG_DIR
```

Use absolute paths for a fresh checkout and a fresh log directory outside that
checkout. Failed checks appear in the JSON with `passed: false`. Setup failures
return a nonzero exit code. The JSON is experiment output and carries no Harborist
Run verification or application authority.

The full application still uses the Python entry points. The Rust foreground
command uses its own arguments, stage evidence and candidate ref namespace.
Continuing started Python Runs, updating publications originally recorded by
Python, integration management, and Docker Sandboxes remain outside the Rust
implementation.

## Rust workflow contracts

The Rust library also implements canonical receipt routing and structured
REVIEW validation. Routing rejects out-of-order receipts, binds TEST and
REVIEW to the BUILD candidate, and routes directly to PACKAGE after a mandatory
check failure. REVIEW validation extracts explicit criterion declarations from
the specification, binds REVIEW to the expected candidate, and requires
exact criterion coverage. A REVIEW receipt does not by itself grant
verification. The Rust foreground runner uses these contracts to validate
the canonical execution order and REVIEW result.

## Foreground benchmark methodology

The script also compares the production Python `run --foreground` command
with the Rust foreground command. Both use the same base commit, Markdown
intent, three mandatory checks, and Codex process fixture. It checks the
candidate tree, invocation order, final outcome, and check logs on every
trial. Commit SHAs can differ because each implementation creates its own
commit. The benchmark includes intake, all workflow stages, and PACKAGE.
The default is two warmups and 20 measured trials per implementation.
The Python path captures additional settings and evidence, so the
comparison includes differences in the work each implementation performs.
It measures orchestration with the fixture and excludes model latency.

## Foreground benchmark result

Docker on Linux ARM64, CPython 3.14.10 and Rust 1.100.0 release build.

| Implementation | Median | p95 |
| --- | ---: | ---: |
| Python | 653.82 ms | 729.79 ms |
| Rust | 120.03 ms | 171.15 ms |

The median speedup for the fixture was **5.45×**.

## Verification-only benchmark result

Docker on Linux ARM64, CPython 3.14.10 and Rust 1.100.0 release build.

| Implementation | Median | p95 |
| --- | ---: | ---: |
| Python | 320.79 ms | 433.20 ms |
| Rust | 8.02 ms | 11.58 ms |

The median speedup was **40.02×** for this fresh-process workload.
The result includes Python imports and process startup. A persistent worker
pays startup once, and long-running checks or model calls could dominate total
Run time. The benchmark does not estimate end-to-end Harborist speedup.
