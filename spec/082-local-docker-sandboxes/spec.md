# Local Docker Sandboxes execution and app policy editing

[GitHub issue #44](https://github.com/maciejgos/harborist/issues/44)

Operators can select Docker Sandboxes execution and edit its policy from
Integrations for a saved Workspace. This implements the local runtime portion
of [Phase 14](../081-workers-and-docker-sandboxes/spec.md). Remote registration,
leases, team authority, scoped repository credentials, and Product persistence
remain planned. The local service still executes one Run at a time through the
synchronous core. Trusted-local execution remains an explicit compatible choice.

## Acceptance criteria

- **AC-1 · App configuration.** Integrations offers a Docker readiness check
  and a Workspace execution-policy editor. Select trusted-local or Docker
  Sandboxes, CPU count (1–16), memory (512–32768 MiB), and additional allowed
  and blocked destinations. Rules accept hostnames, optional `*.` or `**.`
  subdomain prefixes, and optional ports. Reject URLs, credential-bearing
  values, conflicting allow/deny entries, unrestricted wildcards, invalid ports, and unknown fields with
  redacted errors. A save atomically updates only the selected Workspace's
  referenced settings file and preserves its other settings. The browser
  supplies a Workspace ID, never an arbitrary path. Same-origin write guards
  apply. Cancel leaves saved settings unchanged.
- **AC-2 · Frozen policy.** Intake freezes the selected resources, immutable
  Codex kit digest, and allow/deny rules, together with a fingerprint of the
  effective machine-wide Docker policy. The editor saves future defaults; it
  does not modify Docker's global policy or any existing Run. Runtime checks
  reject changed machine authority before provisioning and after a stage.
  Existing trusted-local contracts retain their original serialized shape.
  Rework/recovery use the frozen policy and fresh environments. An intentional
  machine-policy change requires a new capture, not silent migration.
- **AC-3 · Runtime adapter.** Support Docker Sandboxes 0.54.x on a supported
  local host, through an injected `SandboxRuntime` adapter using `sbx`.
  Readiness checks launch no model and return bounded, redacted diagnostics.
  Provision mountless instances with no developer files, Git common directory,
  host SSH agent, shared skills, or MCP integrations. Transfer only committed
  Git state and explicit stage inputs. Missing runtime, login, policy, or
  provisioning capability fails without executing code on the host.
- **AC-4 · Independent execution environments.** Create a fresh VM for each
  DESIGN, PLAN, BUILD, TEST, and REVIEW invocation, attributed to its Attempt.
  No VM or writable cache passes between stages or Attempts. This deliberately
  strengthens the original one-VM-per-Attempt outline: an agent has sudo inside
  its VM, so the TEST environment and REVIEW environment start independently
  from the pinned image and exact committed candidate. Account for provisioning
  and execution in the existing budget; preserve the verification reserve.
- **AC-5 · Native-agent contract.** Use the existing prompts, frozen model and
  reasoning profile, structured stage schema, bounded diagnostics, and final
  output file. Preserve Docker's generated OAuth provider routing without
  loading host user configuration. DESIGN/PLAN/REVIEW use read-only mode.
  Reject a changed starting HEAD or hidden index flags. Export BUILD's bounded
  binary Git patch into the owned host worktree; reject readonly-stage changes.
  Harborist creates the candidate commit and immutable Run-owned ref. Keep a
  complete candidate bundle, digest, size, and candidate attribution outside
  all VMs before TEST. Agent output alone cannot establish verification.
- **AC-6 · Trusted TEST and exact revision.** Execute the frozen mandatory
  commands through a separate sandbox executor; never use the host shell for
  a Docker-selected Run. Collect command exit codes and bounded logs outside
  the VM. Check the candidate revision, index tracking, and changes after TEST;
  disposable ignored files may be cleaned. Mandatory failures block REVIEW.
  REVIEW receives that exact candidate and Harborist's TEST receipt. Existing
  validated lifecycle, criterion coverage, PACKAGE, and verification rules apply.
- **AC-7 · Cancellation, export, and cleanup.** Honor guest deadlines as well
  as host cancellation. Stop/remove the VM itself, not just the `sbx` client.
  Disable cancellation polling during bounded cleanup and inspect resulting
  runtime state. Remove only the owned VM after output and changes have been
  exported. If export is incomplete, retain it stopped with an explicit receipt
  for operator inspection; recovery starts fresh rather than attaching to it.
  Record cleanup failures and package available evidence without claiming
  successful verification. No global reset/prune operations are permitted.
- **AC-8 · Policy boundaries.** Apply saved rules to each new Harborist sandbox
  before repository checkout or model invocation. They supplement the frozen
  machine policy and pinned kit policy; deny rules prevail and an additional
  allow cannot override an existing deny. Use Docker's host-managed OpenAI
  connection; do not copy host Codex credentials or forward `gh` credentials.
  The local operator controls Docker's host credential store. Organization-wide
  credential segregation and remote-worker fencing remain Phase 14 work; this
  increment does not claim production isolation of mutually hostile tenants.

## Validation

Focused tests cover atomic configuration, legacy snapshot compatibility, frozen
baseline rejection, redacted app errors, same-origin guards, command routing,
mandatory-check gating, candidate bundle export, and cleanup during cancellation.
The existing trusted-local suite remains required. A real runtime exercise uses
the pinned kit and bundled methodology to complete the canonical flow and checks
the packaged exact SHA and VM receipts. Browser checks cover readiness, editing,
invalid rules, saving/reloading, and mobile layout.

The local runtime was exercised on 2026-11-19 with `sbx` 0.54.0, Codex 0.170.0,
and an Apple silicon Mac. A disposable greeting Run reached VERIFIED, with TEST
and REVIEW in separate fresh VMs. Preserving Docker's generated `sandboxd`
provider configuration was necessary for OAuth; the trusted-local adapter's
`--ignore-user-config` flag cannot be reused unchanged inside Docker Sandboxes.

See the [implementation verification record](report.md) for the exact test Run,
candidate export, failure/cancellation checks, and browser results.
