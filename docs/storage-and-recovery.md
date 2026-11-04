# Storage and recovery

[Documentation index](README.md) · [Architecture](../ARCHITECTURE.md)

## Storage, workspaces and saved context

Use `uv run shipyard run <run-id>` when running from the development checkout, or install the
`shipyard` entry point on PATH to run the emitted command from any directory.
The locator records absolute resolved repository and Runs-root paths, so the
short command automatically loads `~/.shipyard/runs/<run-id>/execution-context.json`
and selects the captured repository independently of cwd. For custom storage the
emitted command adds only the resolved storage locator, for example:

```bash
shipyard run <run-id> --runs-dir '/absolute/custom runs'
```

Custom storage requires `--runs-dir`: there is no global registry, recursive search,
or discovery across repositories. Commands are quoted for the local POSIX shell,
including spaces and shell metacharacters. Storage inside the target checkout
still requires an external workspace override as described below.

Shipyard resolves its data root from the current user's home directory at command
execution, independently of cwd and the target repository:

```text
~/.shipyard/runs/<run-id>/
  contract.json
  intent.md
  intent.json
  execution-context.json   # CLI invocation locator
  workspace-layout.json    # durable non-contract layout version and Run ID
  execution-workspace.json           # admitted Run/Attempt and resolved workspace path
  run.json
  attempt.json
  events.jsonl
  timing.json
  stage-timings.json
  design/
  plan/
  build/
  test/
  review/
  report.md
  evidence.json
  workspace/               # retained isolated linked Git worktree
```

This changes the separate `runs/<run-id>` and `workspaces/<run-id>` layout
introduced in #5. Each explicit intake creates a distinct Run, even for the same
issue and identical intent digest. Two captures are independent Runs, not the
artifact and workspace halves of one Run. Executing a capture uses its frozen
identity and inputs without recapturing the issue.

Intake creates missing Runs parents on demand; execution creates missing workspace
parents before admitting the Run. Read-only `inspect` and `methodology` never
create missing storage: errors identify the Run and location and advise checking
the Run ID and `--runs-dir`. Different projects share this root with unique Run
IDs. Source checkouts stay in their original locations. Git worktree metadata and
candidate refs may remain in the source repository's Git directory.

`--workspace /fresh/path/outside/checkout` takes precedence over the saved
workspace selection and layout default; it never relocates a capture or changes
its frozen contract. `--runs-dir /path/to/runs` selects capture/evidence storage
and therefore the new default `<runs-root>/<run-id>/workspace`. Context consistency
checks still apply. Only the dedicated workspace child may be placed beneath
Runs storage; stage directories, sibling Runs and ancestors containing records
are rejected. The application executor enforces the same policy as the CLI.
If custom Runs storage lies inside the source checkout, the resulting default
workspace is rejected before admission: supply a fresh external `--workspace`.
There is no silent fallback.

New captures persist `workspace-layout.json` before publishing the frozen
contract. A missing marker identifies a legacy capture; malformed or foreign
markers fail closed. Without an explicit override, recorded workspace selections
remain authoritative (`execution-workspace.json`, or a retained `workspace.json`
selection when present). Admission writes its own create-only execution association
without rewriting a historical selection. Legacy CREATED captures without a
recorded selection use
`~/.shipyard/workspaces/<run-id>` regardless of `--runs-dir`. Existing destinations
remain retained and fail freshness checks, rather than being reused or deleted.
No migration, deduplication, deletion, or ordinary filesystem move of linked
worktrees occurs. Historical evidence without a workspace path stays readable
with its path unknown. No source candidate application is performed here.

Workspaces remain available for inspection; there is no automatic cleanup or
retry of terminal Runs. Terminal Shipyard records and evidence are immutable;
the retained checkout remains mutable. PACKAGE prunes the validated workspace
child before traversal, excluding its `.git` link, repository files and symlinks
from artifact hashing. Evidence outside the workspace keeps strict validation.
CLI JSON, stderr summaries, terminal reports and machine-readable evidence expose
the actual admitted resolved workspace, including overrides and legacy layouts.

Existing destinations (including symlinks) and paths overlapping the resolved
source checkout in either direction fail before the Run leaves CREATED. If the
source contains the default workspace location, supply a fresh external
`--workspace` and retry the captured Run. There is no fallback location. Symlink
aliases are resolved for overlap checks. Directory obstructions and access errors
identify the affected path; correct directory access or choose a valid override.
Shipyard does not overwrite obstructing files or require elevated privileges.

Explicit `--context` takes precedence over automatic lookup and selects its own
repository and storage root when those options are omitted. For both explicit and
automatic contexts, `--repo` and `--runs-dir` constrain the saved locations;
conflicts fail with the expected location. Resolved aliases and repository
subdirectories are accepted:

```bash
shipyard run <run-id> --context /absolute/runs/<run-id>/execution-context.json \
  --repo /path/to/repository --runs-dir /absolute/runs --workspace /fresh/build
# A different --repo or --runs-dir fails with the expected location.
```

A missing or invalid explicit context fails without trying another locator.
An existing invalid or unreadable automatic context also fails before admission,
including directories and dangling symlinks; omitting `--context` cannot bypass it.
Only an absent automatic locator permits the legacy invocation for historical
captures. From elsewhere, supply the repository and any nondefault storage root:

```bash
shipyard run <run-id> --repo /path/to/repository --runs-dir /path/to/runs
```

Existing captures under `~/.shipyard/runs` remain accessible with
`shipyard inspect <run-id>` and `shipyard methodology <run-id>`. For captures in
other locations, add `--runs-dir /path/to/runs` to either command; execute them
with the explicit legacy command above when saved context is unavailable.
Shipyard does not migrate, recapture or backfill context into historical captures,
and terminal Shipyard records remain immutable.

When the automatic context is absent, omitted repository and Runs options select cwd and
`~/.shipyard/runs`; workspace selection follows the capture layout described above.
Moving repositories or Runs storage does not repair locators or permit bypassing
an existing invalid locator. Historical captures without locators use the explicit
legacy invocation; no frozen artifacts are rewritten. The locator is an invocation
hint, separate from `contract.json`, and cannot change the frozen base or settings.

## Persistence guarantees

The PoC uses filesystem-only persistence:

The directory layout is shown in [storage, workspaces and saved context](#storage-workspaces-and-saved-context).

Terminal Shipyard records and evidence are immutable; checkout contents remain mutable.

The implemented `FileIntentStore` persists captured intent under an explicit
Runs root. `intent.md` holds exact UTF-8 bytes; `intent.json` holds only source
reference and artifact metadata. Loading validates the metadata, content identity,
and requested Run ownership through the existing domain contracts without reading
the original issue.

Intent saves create files exclusively and reject either reserved path if present.
The content file is closed before metadata creation. Partial files are retained
on failure and rejected by subsequent load/save operations. This is create-only
intent persistence, without atomic multi-file publication or power-loss guarantees.
The Run store separately owns lifecycle journal persistence and exclusive execution admission.

`FileRunStore` exclusively reserves a fresh Run directory and composes the intent
store with CREATED run.json and complete contract.json. The contract is written
last. Loading requires valid records with matching ownership and identical intent.
Incomplete directories are retained, rejected on load and never overwritten on
save. `begin` exclusively reserves `.execution`, records CREATED/RUNNING events
and updates the Run snapshot. `finish` appends one terminal event and replaces
run.json, requiring matching frozen verification before VERIFIED persistence.
Reload replays validated lifecycle events and rejects snapshot disagreement.
An Attempt cannot be re-admitted or finalized again; explicit continuation
reserves a separate Attempt directory. Journal/snapshot updates
are not transactionally atomic; interrupted writes fail closed and remain
inspectable. OS permissions do not protect against other local writers.

`package_run` reserves `.package` and writes report.md followed by evidence.json.
It records frozen provenance, exact candidate, check results, criterion coverage,
timing, optional provider usage/actual charge and explicit missing evidence.
The index hashes prior regular files with relative paths and sizes, including the
report but excluding itself and the validated dedicated workspace subtree. The
workspace is pruned before traversal, including its `.git` link and repository
symlinks. Symlinks outside the checkout, including a replaced workspace root,
are rejected. External workspace overrides require no subtree exclusion. Editing
a retained checkout does not change or require rewriting terminal evidence. VERIFIED packaging reconciles
DESIGN/TEST/REVIEW against the terminal verification record. No model participates
in packaging and no execution allowance is required. Disk errors are surfaced;
partial PACKAGE is retained and cannot be silently retried.

## Phase 10 delivery persistence

The background service stores delivery snapshots separately in
`~/.shipyard/control/queue`. Run/Attempt evidence remains in the existing Runs
root. Queue snapshots are locked and atomically replaced; they do not make Run
journals, Git and PACKAGE transactional. Interrupted claims are retained without
automatic retry, session resume or evidence mutation. See the
[background service guide](background-control-plane.md) for restart and shutdown
semantics. Explicit Phase 11 recovery creates a separate Attempt as described below.

## Phase 11 attempt persistence

The original Run directory remains the first Attempt's immutable evidence. Later
Attempts live under `<runs-root>/<run-id>/attempts/000001`, `000002`, etc. Each has
copied frozen contract/intent/layout, a create-only `continuation.json`, bounded
`continuation-context.json`, optional `frozen-spec.md`, independent `run.json`,
`attempt.json`, lifecycle journal, captures, timing and PACKAGE. The root locator
is never moved. Normal RunStore reads select the highest contiguous number;
explicit numbered stores can inspect history. Gaps, symlinks and malformed or
incomplete latest captures are errors, never fallback to an older VERIFIED result.

Admission holds an advisory lock on the original directory inode, checks the
expected predecessor, digests and attribution, then creates the next directory
exclusively. Execution holds the same lock. This is a local POSIX lock and
filesystem-only protocol, without a multi-file transaction or power-loss repair.
Terminal predecessor records are not reopened or overwritten. An interrupted
RUNNING snapshot remains historical; explicit recovery records a fresh Attempt
and the interruption in its continuation receipt.

Frozen specs come from checked PACKAGE indexes or a complete ready DESIGN
manifest with matching request/profile/guidance, artifact hashes and ownership.
An inherited spec remains fixed even if a later Attempt lost its worker.
Incomplete DESIGN output is never accepted as a spec. Prior TEST/REVIEW is context
only; the new Attempt must establish its own exact-candidate verification.
Continuation receipts retain cumulative spending, all explicit grants and input
digests. Missing reliable terminal timing charges the previous allowance in full.

Later default checkouts live outside evidence at
`<runs-root-parent>/workspaces/<run-id>/<attempt-id>`. All earlier checkouts and
candidate refs remain retained. Later candidates have create-only Attempt refs,
while the original Run candidate ref continues to identify the first candidate.
Application resolves the latest Attempt's exact ref and verification evidence.

The service archives earlier delivery snapshots in
`<control-root>/deliveries/<run-id>/<request-id>.json` (`initial.json` for the
original submission). Queue records remain separate from validated lifecycle.
Replaying a retained request returns its prior delivery; it cannot create an
Attempt. New continuation requests are checked both at submission and execution.
