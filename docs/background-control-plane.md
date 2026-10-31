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
socket is local-only; HTTP JSON is also the web read model. A browser frontend,
TCP listener, remote authentication and team access are outside this slice.

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

GET /health, GET /runs and GET /runs/{uuid} read persisted records. Progress is
observational and may lag; validated lifecycle and immutable terminal evidence
are authoritative. Concurrent lifecycle writes may temporarily yield an explicit
unavailable status rather than fabricated state. Artifact references are paths,
not an unrestricted file download endpoint.

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
Interrupting the viewer leaves the service running. Listings include only
submitted Runs in the selected service, not every capture on disk.

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
limited to 64 KiB. No arbitrary artifact downloads or TCP listener are exposed.
`package_available` means both terminal files are present; it does not rehash
artifacts or grant verification. Explicit apply continues to validate evidence.

## Phase 10 acceptance

Specifications 050–057 cover the complete slice sequence. Integration tests use
real processes, Unix sockets, filesystem storage, Git and deterministic checks;
only native-agent responses are replaced. They verify client exit, VERIFIED
packaging, duplicates, graceful drain, owner exclusivity and forced-kill restart.
They do not exercise live paid agent calls, OS boot/login supervision or power
loss. The service is supported on local Unix systems with flock and Unix sockets.
