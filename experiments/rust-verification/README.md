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
harborist-verify run REPO BASE_SHA INTENT_FILE NEW_RUN_DIR
```

Use an exact base commit and a fresh Run directory outside the source checkout.
The checkout must have Git author identity configured. The runner freezes the
Markdown intent and base revision's verification config, then invokes fresh
Codex processes for DESIGN, PLAN, BUILD, and REVIEW. It commits BUILD in a
detached worktree, runs trusted checks, and opens a clean worktree for REVIEW.
A check failure or tracked checkout change prevents REVIEW. PACKAGE writes
`report.md` and `evidence.json` under the Run directory. The Run's candidate ref
keeps the candidate reachable after worktree cleanup.

The adapter uses the installed Codex CLI's default model. The Docker suite
exercises the adapter with a deterministic executable fixture. It has no
credentials and makes no external model calls.

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
It also checks failure, timeout, output truncation and strict YAML field types
outside the timed workload.

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
Python settings and methodology capture, persisted-run execution, recovery,
the background service, browser adapter, application, GitHub integrations,
legacy YAML compatibility, worker cancellation, and Docker Sandboxes remain
outside the Rust foreground implementation.

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
| Python | 658.68 ms | 792.35 ms |
| Rust | 112.37 ms | 160.69 ms |

The median speedup for the fixture was **5.86×**.

## Verification-only benchmark result

Docker on Linux ARM64, CPython 3.14.10 and Rust 1.100.0 release build.

| Implementation | Median | p95 |
| --- | ---: | ---: |
| Python | 309.01 ms | 399.63 ms |
| Rust | 7.94 ms | 10.47 ms |

The median speedup was **38.93×** for this fresh-process workload.
The result includes Python imports and process startup. A persistent worker
pays startup once, and long-running checks or model calls could dominate total
Run time. The benchmark does not estimate end-to-end Harborist speedup.
