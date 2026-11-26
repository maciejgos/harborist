# Rust verification experiment

This branch ports Harborist's trusted-local verification slice to Rust as a
standalone Linux executable. It reads version 1 checks from `harborist.yaml`
at a supplied base commit, checks out an exact candidate in a detached Git
worktree, runs every check in order, and emits JSON and bounded log files.
The experiment uses fresh local Git repositories inside Docker and runs with
container networking disabled. It expects trusted check commands.

## Run the comparison

From the repository root with Docker running:

```sh
./experiments/rust-verification/docker-exercise.sh
```

The script builds the existing Harborist Python runtime and compiles the Rust
binary in a separate build container. The parity check and both timed commands
then run in the same Linux container, with a two-CPU limit. There are no model
calls, external repositories, or host mounts with write access during timing.

Each trial starts a fresh process, reads and hashes the frozen config, creates a
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

The experiment covers only trusted-local TEST. The synchronous workflow,
native-agent stages, Run and Attempt persistence, background service, browser,
and delivery integrations still run in Python. Legacy `shipyard.yaml` loading,
Python YAML edge cases, worker cancellation, and Docker Sandboxes are outside
the comparison.

## Measured result

Docker on Linux ARM64, CPython 3.14.10 and Rust 1.100.0 release build.

| Implementation | Median | p95 |
| --- | ---: | ---: |
| Python | 311.01 ms | 372.51 ms |
| Rust | 7.68 ms | 9.64 ms |

The median speedup was **40.48×** for this fresh-process workload.
The result includes Python imports and process startup. A persistent worker
pays startup once, and long-running checks or model calls could dominate total
Run time. The benchmark does not estimate end-to-end Harborist speedup.
