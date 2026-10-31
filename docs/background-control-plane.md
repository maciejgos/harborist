# Phase 10 background control plane

## Decision and scope

Phase 10 is authorized by the owner on 2026-10-31. This authorizes a local
background service, queue, CLI client and web read model. It does not declare
Phase 9's matched direct-Codex comparison or trust evaluation complete; that
work remains tracked in the 2026-10-30 validation audit.

The execution core remains synchronous. One service executes one Run at a time
through execute_run, with the existing NativeAgent, Git, TEST and RunStore
boundaries. No database, distributed worker, automatic rework or publication is
introduced. The explicit foreground mode remains available for compatibility.

## Contract

A control directory owns an advisory process lock, an owner-only Unix HTTP
socket, an atomic filesystem queue and a stop signal in service memory. The
socket is local-only; HTTP JSON is also the web read model. A separate read-only
browser adapter serves the dashboard on 127.0.0.1. Remote authentication and
team access remain outside this slice.

POST /runs accepts versioned execution locators for an already captured Run.
Intake remains a CLI operation and freezes inputs before submission. Run UUID is
the idempotency key within this control directory. Repeating an identical
submission returns the existing record; conflicting locators fail. Requests
must name resolved absolute paths. Only CREATED Runs may be newly submitted.
Queue order is submission time then UUID. Queue wait does not consume the frozen
execution budget. Work is claimed durably before executor admission.

Submission states are QUEUED, RUNNING, FINISHED, FAILED and INTERRUPTED. These
are service delivery states, not replacements for RunLifecycle or RunOutcome.
FINISHED means the executor returned packaged evidence, not VERIFIED. FAILED
means the executor raised; retained Run records remain authoritative.
INTERRUPTED means service ownership was lost after claim. Restart never retries
or resumes it, even if the Run still appears CREATED or terminal. Operators
inspect retained records and use a fresh intake where necessary (Phase 11 will
provide recovery rules). A crash after PACKAGE but before queue completion may
therefore show INTERRUPTED beside a valid terminal Run.

GET /health, GET /runs and GET /runs/{uuid} read persisted records. Run history
combines UUID captures under ~/.shipyard/runs with service submissions. Progress is
observational and may lag; validated lifecycle and immutable terminal evidence
are authoritative. Concurrent lifecycle writes may temporarily yield an explicit
unavailable status rather than fabricated state. Artifact references identify packaged files. An allowlisted GET endpoint serves
only report.md and evidence.json as bounded plain text for the browser adapter.

POST /stop stops new submissions and claims, drains the current execution and
leaves queued work intact. A forced kill may leave subprocesses alive; restart
classifies claims as interrupted and never launches replacements. Advisory locks
prevent duplicate service owners; FileRunStore admission still prevents duplicate
Run execution across foreground and service paths. Independent control
directories are not a distributed scheduling system.

The HTTP protocol is version 1, bounded JSON requests with explicit validation
errors and no cross-origin permission headers. The Unix socket inherits a private
control directory and mode 0600. Local filesystem owner is the trust boundary.

## Operation

```bash
uv run shipyard service start
uv run shipyard run file:examples/intake/issue.md
uv run shipyard runs
uv run shipyard status <run-id> --wait
uv run shipyard service status
uv run shipyard service stop
```

`start` detaches a new process and waits for readiness. Repeating it while the
service is healthy is harmless. `serve` runs in the foreground for a supervisor.
The service inherits the launching user's environment and agent credentials;
restart after changing credentials or environment. `stop` requests a drain and
returns immediately; health reports `stopping` until the active Run finishes.
The socket disappears after shutdown. SIGTERM/SIGINT also request a drain.
A supervisor should allow the full frozen Run budget plus packaging time.

Use `--control-dir PATH` consistently for service, run, runs and status commands
to select another service. Unix socket paths have OS length limits; choose a
short local path if startup reports a path-length error. Runs directories remain
selected by `--runs-dir`; submissions store absolute execution locators.

Background `run --json` returns a delivery record. Its zero exit code means
accepted, not VERIFIED. `status --json` adds validated Run state, Attempt ID,
observational progress and package file availability. `status --wait` polls and
returns the terminal delivery record; it also exits zero for a successful read,
regardless of software outcome. Inspect `run.outcome` and `run.failure_reason`.
Interrupting the viewer leaves the service running. Listings include saved Runs
under ~/.shipyard/runs and submissions in the selected service.

`run --foreground` retains the former synchronous output and terminal exit codes
(0 VERIFIED, 2 other software outcomes, 1 execution failure, 130 cancellation).
Scripts relying on synchronous behavior must add `--foreground`. Source intake
and saved UUID execution options remain available. `inspect`, `methodology` and
`apply` remain explicit local operations; the web interface is read-only apart
from submission and graceful service-stop endpoints.

A missing service produces a start command and retains the capture. Submit its
UUID after starting the service rather than recapturing the request. Delivery
FAILED or INTERRUPTED records are never requeued by repeating the submission;
inspect retained records, then use a fresh intake if execution is needed again.
No previous candidate's verification transfers to that new Run.

## Storage and HTTP

Default control storage is `~/.shipyard/control`:

```text
control/
  service.lock       # OS advisory ownership, not a PID file
  service.sock       # HTTP over a mode-0600 Unix socket
  service.log        # detached process diagnostics
  queue.lock         # serializes snapshot readers and writers
  queue/<uuid>.json  # durable delivery status and progress
```

Snapshots publish by temporary-file replacement, with file and directory fsync.
This is local filesystem durability, not a transaction with Git, Run journals or
PACKAGE. A crash can leave an interrupted delivery alongside complete evidence;
inspect the Run independently. Temporary snapshots left before replacement are
ignored. Corrupt published queue records fail closed and require inspection.

For direct API access (for example a local web adapter):

```bash
curl --unix-socket "$HOME/.shipyard/control/service.sock" http://localhost/health
curl --unix-socket "$HOME/.shipyard/control/service.sock" http://localhost/runs
curl --unix-socket "$HOME/.shipyard/control/service.sock" http://localhost/runs/<run-id>
```

Submission JSON has `version: 1`, `run_id`, `repository`, `runs_root` and optional
`workspace`, with absolute resolved paths. POST `/runs` returns its durable queue
record. POST `/stop` returns `{"stopping": true}`. Unsupported routes, malformed
bodies and invalid records return explicit JSON errors. Request bodies are
limited to 64 KiB. No arbitrary artifact downloads are exposed. The execution service stays on
its Unix socket; the browser adapter is loopback-only and read-only.
`package_available` means both terminal files are present; it does not rehash
artifacts or grant verification. Explicit apply continues to validate evidence.

## Phase 10 acceptance

Specifications 050–057 cover the complete slice sequence. Integration tests use
real processes, Unix sockets, filesystem storage, Git and deterministic checks;
only native-agent responses are replaced. They verify client exit, VERIFIED
packaging, duplicates, graceful drain, owner exclusivity and forced-kill restart.
They do not exercise live paid agent calls, OS boot/login supervision or power
loss. The service is supported on local Unix systems with flock and Unix sockets.


## Browser execution monitor

Start (or upgrade and restart) the service, then launch the monitor in another
terminal:

```bash
uv run shipyard service start
uv run shipyard web
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Submit work from another
terminal with `shipyard run`. The dashboard shows submitted Run history,
search, selected Run details, the seven-stage timeline, lifecycle/outcome,
Attempt ID, verified candidate SHA and report/evidence viewers. It polls every
two seconds. Closing the browser or stopping `shipyard web` leaves the execution
service and active Runs running.

The monitor is a thin adapter over the canonical control plane. Browser GETs
under `/api` proxy only health, Run listing/detail and the two named artifacts.
No submission, shutdown, apply or recovery mutations are exposed by the web
adapter. Its loopback binding and Host validation keep it local. No framework,
Node build, hosted service or separate state store is required.

Use `shipyard web --control-dir PATH --port 8766` to select another service or
port. The control directory must match `service start` and `run`. An unavailable
service has an explicit retry state; failed refreshes retain prior data with a
stale-data warning. Selection and search survive polling and reconnects. Reports
are shown as plain text in a keyboard-accessible dialog, never interpreted as
HTML. Artifact viewing is limited to 2 MiB per file and rejects symlinks.

Existing queue snapshots remain compatible. Older records without stage history
show **Not recorded** for missing observations; they never appear successful by
inference. INTAKE completion reflects a validated frozen capture. Per-stage
observations are separate from authoritative lifecycle and verification. Restart
an older running service after upgrading to enable stage history and artifact
endpoints; let active work finish before a normal upgrade/restart.

The dashboard and `shipyard runs` discover all saved Run directories under
`~/.shipyard/runs`, including earlier foreground executions and CREATED captures,
then merge service submissions without duplicates. No import, queue insertion,
source checkout or execution-context locator is required. Individual details and
the report/evidence viewers work for historical Runs too.

Read responses identify `source: "saved"` or `source: "service"`. A saved Run has
`state: null` and `submitted_at: null`, because it has no service-delivery record.
Its lifecycle/outcome still comes from validated FileRunStore records. Recorded
and updated times use contract/run file modification timestamps for legacy
captures; these timestamps order the view and never confer execution authority.
Queue submission/update times remain authoritative for service delivery.
Historical stage observations are not fabricated; absent progress is shown as
Not recorded. `status --wait` returns immediately for a terminal historical Run.

Discovery never executes, repairs or changes a Run. Missing roots are empty;
unrelated files and symlink directories are ignored. Partial/corrupt UUID
captures appear unavailable without hiding valid history. An identical Run in
the queue and saved root appears once, using actual delivery metadata. Conflicting
UUIDs in different roots fail explicitly rather than mixing candidate evidence.
Arbitrary custom Runs roots are not globally scanned; service submissions retain
access to their explicitly recorded roots. Restart an older running service after
active work finishes to enable expanded history discovery.
