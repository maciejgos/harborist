# Phase 14 workers and Docker Sandboxes

[GitHub issue #44](https://github.com/maciejgos/harborist/issues/44)

Product workers execute Attempts in fresh Docker Sandboxes microVMs. A worker
may run on a different machine from the control plane; sandbox compute stays
local to that worker. Docker Sandboxes replaces the phase outline's generic
Docker adapter choice. The [local runtime and app policy editor](../082-local-docker-sandboxes/spec.md)
are implemented as an initial increment. Existing captures retain explicitly
labeled `trusted-local` execution; new captures can select Docker Sandboxes.

This is the Phase 14 acceptance contract, expanding
[Product Milestone 1](../067-team-product/spec.md#phase-14-workers-and-sandboxes)
and [PRD §§52–58](../../docs/Product%20Requirements%20Document%20v1.0.md#52-credential-separation).
Phase 13 supplies Organization, Project, and actor authority. Phase 15 supplies
Product persistence, retention, and publication reconstruction. Docker-managed
cloud compute, other sandbox providers, scheduler fairness, and a new public API
are outside this phase. Remote-worker acceptance remains planned; the local
increment does not change existing frozen Runs or complete this whole phase.

## Acceptance criteria

- **AC-1 · Worker registration and compatibility.** Only authenticated workers
  authorized for the Organization can register, pull work, renew ownership,
  or submit results. Record worker identity, protocol version, architecture,
  CPU/memory capacity, Docker Sandboxes runtime/version, and Codex capability.
  Track current availability separately from those compatibility requirements.
  Assign only work whose frozen requirements the worker satisfies. Reject
  incompatible protocol/runtime versions before execution. Report
  `UNSCHEDULABLE` when no registered worker meets the requirements; compatible
  workers that are busy or offline leave work `QUEUED`. Project languages and
  frameworks remain repository/environment concerns, not scheduler metadata.
- **AC-2 · Exclusive pull leases.** Workers pull eligible work and the control
  plane atomically grants at most one current lease for an Attempt. Every
  heartbeat, progress update, artifact submission, and completion identifies
  the Run, Attempt, worker, and lease generation. Renewal and completion reject
  expired, revoked, mismatched, or superseded leases. Duplicate messages for
  the same accepted operation are idempotent. Concurrent claims cannot start
  two owners, and stale messages cannot overwrite newer Attempt evidence.
- **AC-3 · Uncertain ownership and recovery.** Lease expiry or lost worker
  contact records `RECOVERY_REQUIRED` as delivery/ownership state, separate
  from validated Run lifecycle and software outcome. It never proves execution
  stopped and never automatically requeues or duplicates the Attempt. On failed
  renewal, the worker stops admitting stages and attempts to stop its sandbox.
  Explicit authorized recovery fences the old lease and execution credentials
  and establishes that the old sandbox is stopped or isolated before starting
  a fresh Attempt. If that cannot be established, recovery stays blocked with
  an actionable reason. Preserve earlier evidence and the existing frozen
  contract, continuation rules, spent time, and explicit budget grants.
- **AC-4 · Runtime boundary and Docker Sandboxes adapter.** A small injected
  `SandboxRuntime` boundary owns readiness, creation, command execution,
  bounded file transfer, stop, inspection, and removal. Its first Product
  adapter uses the standalone Docker Sandboxes `sbx` CLI in local mode on the
  worker. Ordinary `docker run`, Docker Compose services, and native Codex
  permission flags do not satisfy sandbox isolation. Keep Docker command
  syntax, identifiers, and errors in the adapter; preserve `NativeAgent`,
  system Git, and trusted verification boundaries. Document and test the
  supported `sbx` version and worker platform prerequisites. Readiness checks
  run in the worker service environment and distinguish missing/unsupported
  runtime, unavailable virtualization/daemon, missing credentials, and failed
  provisioning. They launch no model execution. Fail without host fallback.
- **AC-5 · Frozen execution environment.** Freeze the runtime kind, supported
  version requirement, immutable template/kit references, resource limits,
  network profile and rules, and credential references with the Run. Secrets
  are resolved at execution and never frozen as values. Record actual runtime
  version, resolved image/kit digests, worker and sandbox identity, and effective
  policy in Attempt evidence. Reject an environment that cannot satisfy the
  frozen contract. Configuration changes affect future captures; they cannot
  silently change queued Runs, active Attempts, or continuations. Legacy
  `trusted-local` captures retain their semantics and cannot be relabeled as
  sandboxed or silently migrated.
- **AC-6 · Fresh sandboxes owned by one Attempt.** Provision unique mountless
  sandboxes and populate private repositories at the exact Attempt start SHA.
  Agent stages, trusted TEST, and independent REVIEW use separate fresh VMs
  so an earlier stage cannot contaminate the next stage's tools or processes.
  Initial Attempts use the frozen base; rework and recovery use their validated
  continuation inputs. Never attach to an existing sandbox on a naming
  collision or reuse an earlier Attempt's VM, agent sessions, writable volumes,
  or caches. Do not mount the developer checkout, its Git common directory,
  Harborist control/evidence storage, host Docker socket, home configuration,
  or SSH agent. Disable shared agent skills and MCP access; supply only frozen
  Harborist methodology. Developer staged, unstaged, untracked, and ignored
  files remain untouched and are not copied into execution.
- **AC-7 · Canonical execution and verification.** The worker invokes the
  synchronous execution core with `INTAKE → DESIGN → PLAN → BUILD → TEST →
  REVIEW → PACKAGE`; it does not create a second workflow engine. DESIGN,
  PLAN, BUILD, and REVIEW use fresh noninteractive native-agent processes,
  validated structured output, and the frozen model/profile. BUILD cannot
  change the frozen acceptance spec. Harborist creates and records the candidate
  commit, runs the frozen mandatory TEST commands against that exact SHA, and
  blocks REVIEW on mandatory failure. REVIEW is independent and read-only.
  Keep runner control and authoritative receipts outside agent-writable state;
  an agent-written file or sandbox exit status cannot establish verification.
  Stop earlier stage processes before advancing and detect candidate changes
  during TEST/REVIEW. Changed code requires fresh TEST and REVIEW. Preserve
  existing outcomes, budget reserve, bounded logs, and PACKAGE behavior.
- **AC-8 · Network authority.** Support frozen `restricted` and `standard`
  profiles; `restricted` is the default for Product execution and allows only
  explicitly required repository, model-provider, and dependency destinations.
  `standard` is an explicit compatibility choice with recorded rules. Apply
  and inspect effective policy before repository code or an agent runs; host
  defaults and kit rules cannot silently widen it. Reject unsupported policy
  enforcement. The agent cannot change policy, enable integrations, or obtain
  access to worker/control-plane administration. Policy changes require a new
  authorized capture, not an agent request during execution.
- **AC-9 · Scoped execution credentials.** Resolve temporary repository-read
  credentials for the selected Project and Attempt; permit clone/fetch and
  reject push, PR creation, and merge. Bind model-provider access to the
  Attempt's approved connection. Use sandbox-scoped host proxy injection for
  supported services and prevent inheritance of unrelated global credentials.
  Publication credentials remain in the delivery component outside workers
  and sandboxes. Do not forward the operator's `gh` login, host credential
  helpers, or SSH signing authority. Revoke execution access on lease loss,
  cancellation, and completion without falling back to a broader credential.
  Persist references and redacted diagnostics, never raw secrets in domain
  records, command arguments, logs, artifacts, or audit records. A credential
  failure remains distinguishable from a software check failure.
- **AC-10 · Cancellation, deadlines, and failures.** Queue waiting does not
  consume execution budget; provisioning and execution do. Honor cancellation
  and the remaining execution deadline inside the VM. Killing the host `sbx`
  client alone is insufficient: stop sandbox processes and confirm their
  termination, or record uncertain ownership for recovery. Attempt PACKAGE
  outside execution budget for every terminal path, including provisioning,
  agent, TEST, and runtime failures. Failed transfers or unavailable workers
  leave missing evidence explicit; they cannot produce successful completion
  or VERIFIED. Cleanup uses a separate bounded operational timeout.
- **AC-11 · Export before completion and destruction.** Before accepting
  completion, export available stage artifacts, structured results, TEST and
  REVIEW receipts, bounded diagnostics, provenance, and PACKAGE evidence to
  control-plane-accessible durable storage outside the sandbox. Phase 14 may
  use filesystem-backed storage; an unacknowledged worker-local copy is not
  sufficient. When a candidate exists, export a Git bundle or equivalent
  complete Git object artifact with its exact candidate/start
  and frozen base SHAs, Run/Attempt attribution, artifact reference/version,
  digest, and size. Validate ownership, integrity, and required completeness
  outside the sandbox and acknowledge durable export under the current lease.
  Early outcomes without a candidate export their available evidence and an
  explicit absent-candidate reason. Retrying export is idempotent and never
  reruns stages or overwrites accepted evidence. Failed export blocks accepted
  completion and normal destruction; retain a stopped sandbox for explicit
  recovery. Phase 15 provides the Product storage adapter and retention policy.
- **AC-12 · Cleanup and observable state.** Remove only the sandbox owned by
  the selected Attempt after acknowledged export; never run global prune/reset
  operations. Confirm removal through runtime inspection, since a stop or a
  successful removal request alone does not establish destruction. Record
  cleanup failure separately from the validated software outcome and retain
  evidence for an authorized cleanup retry. Expose worker readiness, lease and
  heartbeat state, scheduling reason, runtime/sandbox identity, export state,
  and cleanup errors through the control plane for CLI/browser inspection.
  Displaying these observations never grants lifecycle transitions or
  verification.

## Validation

Automated checks use small runtime/worker/credential fakes for concurrent lease
claims, idempotent delivery, stale renewals/results, capability mismatch, busy
workers, lease loss, blocked recovery, cancellation, provisioning failure,
credential expiry, policy rejection, export retry/failure, and cleanup failure.
They verify exact-revision TEST/REVIEW gates and unchanged trusted-local behavior.

Focused integration checks on a documented supported worker use real system Git
and Docker Sandboxes to create a mountless VM, run fresh Codex stage processes
with schema-conforming outputs, execute a failing mandatory check that blocks
REVIEW, enforce an allowed and denied network destination, reject repository
writes to GitHub, and stop execution on cancellation/deadline. Prove isolation
from developer files, host credentials, shared skills, MCP, and prior Attempts.
Use a disposable repository and scoped test credentials; retain redacted receipts
with the tested runtime/platform versions. Environments without Docker Sandboxes
report these checks as unverified rather than treating fakes as integration proof.

An end-to-end worker-loss exercise demonstrates `RECOVERY_REQUIRED`, rejection
of stale completion, explicit recovery into a different sandbox, and no automatic
duplicate assignment. An export exercise destroys an acknowledged sandbox and
imports its candidate artifact into an empty repository, confirming the exact
SHA and evidence digests. Tampered or incomplete exports are rejected. Phase 15
must repeat this durability proof with its Product storage implementation.

## Docker reference baseline

Checked against Docker documentation on 2026-11-19. These references describe
provider capabilities; the acceptance criteria above define Harborist policy.

- [Docker Sandboxes overview](https://docs.docker.com/ai/sandboxes/) and
  [local/cloud differences](https://docs.docker.com/ai/sandboxes/cloud/local-vs-cloud/).
- [Create](https://docs.docker.com/reference/cli/sbx/create/),
  [exec](https://docs.docker.com/reference/cli/sbx/exec/), and
  [remove](https://docs.docker.com/reference/cli/sbx/rm/) CLI contracts.
- [Security model](https://docs.docker.com/ai/sandboxes/security/),
  [default posture](https://docs.docker.com/ai/sandboxes/security/defaults/), and
  [credential management](https://docs.docker.com/ai/sandboxes/configuration/credentials/).
- [Codex integration](https://docs.docker.com/ai/sandboxes/agents/codex/) and
  [headless execution](https://docs.docker.com/ai/sandboxes/workflows/automation/).
