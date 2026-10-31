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
