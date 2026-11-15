# Draft specification: Product Milestone 1

Source: [PRD §§91–98](../../docs/Product%20Requirements%20Document%20v1.0.md#91-product-milestone-1-definition). Phase numbers follow the PRD dependency order.

## Phase 13 Team identity and GitHub App

- Model one Organization, Users with Admin, Operator, or Viewer roles, and Projects mapped to repositories.
- Authenticate and deduplicate GitHub App webhook deliveries. Map each state-changing command to a stable actor and enforce the same authority as other clients.
- Reject unauthorized commands and require an explicit Project when the target is ambiguous.

## Phase 14 Workers and sandboxes

- Register remote workers and match work to capabilities using pull leases and heartbeats. Surface unschedulable work and require explicit recovery after uncertain lease loss.
- Run each Attempt in a fresh sandbox through a runtime boundary with a Docker adapter, network policy, and temporary execution credentials. Keep publication credentials outside execution.
- Require candidate and evidence export before accepting Attempt completion. Verify that lease expiry cannot silently duplicate execution.

## Phase 15 Product persistence

- Store control-plane records in PostgreSQL. Use an ArtifactStore for evidence and candidate bundles, with integrity checks and a defined retention policy.
- Prove that a VERIFIED candidate can be reconstructed at its exact SHA after its sandbox is destroyed. Reject tampered or incomplete evidence.

## Phase 16 Scheduling and governance

- Support queued reprioritization, priority aging, Project fairness, and Organization and Project concurrency limits. Lowering a limit leaves active Attempts running.
- Version and audit execution policies and operational settings. Freeze execution semantics for queued and active Runs.
- Govern immutable playbook and skill versions, Agent Connections, and execution profiles. Admins control activation and rollback. Projects can pin approved methodology versions for pilots.

## Phase 17 Headless public control plane

- Expose a versioned REST control plane used by the CLI, web UI, and MCP. Authorize Service Accounts explicitly and record their own actor identities.
- Exercise every first-party mutation through the supported API and verify equivalent authority checks and domain effects.

## Phase 18 Operations

- Support portable self-hosting with Docker Compose as the minimum deployment. Record auditable actions, structured telemetry, and notifications for decisions and material events.
- Resolve secrets just in time through SecretProvider. Support credential rotation and distinguish credential failures from execution failures.
- Define backup and restore across domain data and artifacts, recovery-degraded behavior, drain and upgrade procedures, and worker protocol compatibility. Run restore and upgrade drills before acceptance.

## Phase 19 Analytics and learning

- Produce a scorecard and Project and Organization findings for trust, adoption, reliability, and efficiency using recorded outcomes.
- Link recommendations and proposed methodology or configuration changes to their evidence. Require explicit human activation of any change.

## Product acceptance

- Demonstrate end-to-end authority checks, exact-candidate publication, durable evidence, safe recovery after worker loss, and successful restore and upgrade drills.
- Validate repeated use with at least one real team over multiple weeks. PRD targets include three Projects, 30 completed Runs, 15 published PRs, multiple merged PRs, two rework flows, two recovery flows, and a cancellation or supersession path.
- Record whether Operators voluntarily return and reviewers use the evidence as part of normal engineering work.
