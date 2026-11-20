# Storage and recovery

Find saved Runs, worktrees, and delivery records. Use the Run UUID when
inspecting evidence or recovering from an interrupted execution.

## Find Run and service data

The default data directory is `~/.harborist`, shared by projects under the
same OS account.

| Path relative to the data directory | Contents |
| --- | --- |
| `runs/RUN_ID/contract.json` | Frozen base revision, request, configuration, and execution inputs. |
| `runs/RUN_ID/intent.md` | Captured request text. |
| `runs/RUN_ID/run.json` and `events.jsonl` | Validated lifecycle snapshot and event journal for the first Attempt. |
| `runs/RUN_ID/{design,plan,build,test,review}/` | Available stage artifacts and diagnostics for the first Attempt. |
| `runs/RUN_ID/report.md` and `evidence.json` | Packaged report and hashed evidence index for the first Attempt. |
| `runs/RUN_ID/attempts/` | Evidence for later Attempts. |
| `runs/applications/` and `runs/publications/` | Local application receipts and GitHub delivery records. |
| `control/service.log` | Detached service diagnostics. |
| `control/queue/` and `control/deliveries/` | Current queue records and archived deliveries. |

Normal status and reports refer to the latest Attempt. For earlier Attempts,
open the Run in the browser workspace and select the Attempt you want to
inspect. The queue history records delivery separately from Run evidence.

## Storage, workspaces and saved context

Set `--runs-dir PATH` at capture to save Runs outside the default directory.
Pass it again when looking up the Run. For example:

```bash
harborist inspect RUN_ID --runs-dir '/srv/harborist/runs'
harborist run RUN_ID --runs-dir '/srv/harborist/runs'
```

The second command submits a saved `CREATED` Run. Its
`execution-context.json` selects the original repository regardless of the
current directory. Use `--context PATH` to supply the locator explicitly. If
you also pass `--repo` or `--runs-dir`, they must match the locations in the
locator. Missing explicit or invalid saved locators cause an error. Historical
captures with no locator can use an explicit `--repo` and `--runs-dir`.

The first Attempt normally creates a linked Git worktree at
`<runs-root>/RUN_ID/workspace`. A later Attempt normally uses
`<runs-root-parent>/workspaces/RUN_ID/ATTEMPT_ID`. Existing captures keep their
recorded layout. Set `--workspace PATH` if you need a different location:

```bash
harborist run RUN_ID --runs-dir '/srv/harborist/runs' --workspace /path/to/fresh-worktree
```

Choose a fresh path outside the source checkout. Inside Runs storage, only
the Run's dedicated workspace directory is eligible. If a destination
already exists or overlaps the source, choose a new location and retry the
saved Run. Worktrees and candidate refs are retained for inspection.

## Evidence integrity

Harborist writes `report.md` before `evidence.json`. The evidence index
records artifact paths, sizes, and SHA-256 digests. It covers the report and
packaged artifacts. The retained workspace and the index itself are excluded.

The candidate is the commit identified in the evidence. Editing the retained
worktree cannot change that commit's verification record. Application checks
the candidate ref and packaged evidence before advancing a branch.

A filesystem or process failure can leave partial artifacts. Harborist
rejects inconsistent lifecycle records and incomplete or malformed latest
Attempts. Use available logs and artifacts to diagnose the failure. A missing
report or incomplete index calls for inspection before delivery.

## Attempt history

The first Attempt's evidence stays at the Run root. Later Attempts are numbered
`attempts/000001`, `attempts/000002`, and so on. Each records its own execution,
candidate, verification evidence, and continuation details.

A continuation may reuse a validated `spec.md` from the previous Attempt.
It must establish verification for its own candidate through fresh TEST and
REVIEW. Continuation records also capture cumulative time spent and any
explicit time grants.

## Recover after an interruption

1. Check `harborist status RUN_ID` and inspect any saved report and evidence.
   An `INTERRUPTED` delivery can accompany a completed Run if the service
   stopped after packaging.
2. Ensure the old executor has stopped. The service keeps the delivery
   record and does not automatically retry a claimed Run on restart.
3. For an eligible failure, use [explicit recovery](usage.md#rework-and-recovery).
   Worker loss or missing terminal timing requires an additional time grant.
   Recovery creates a new Attempt and preserves earlier evidence.
