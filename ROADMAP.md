# Shipyard roadmap

Shipyard can already take a request from a Markdown file or GitHub issue, run it in a separate Git worktree, and verify the exact commit it produces. The local service runs one job at a time in the background. You can follow it from the CLI or browser, and Phase 11 added a way to rework or recover a Run without starting over.

The local MVP adds a browser workspace for day-to-day operation. Every screen follows a shared React and shadcn/ui design, using Linear as the reference for information density, navigation, and keyboard interaction. MVP acceptance includes the browser workflow from intake through recovery and approved GitHub delivery.

Team features come after the local MVP. The first product milestone is to get a real engineering team using Shipyard repeatedly across several repositories.

The proof of concept uses the current package version in [pyproject.toml](pyproject.toml). The MVP and Product version numbers are proposed targets. See the [Product Requirements Document v1.0](docs/Product%20Requirements%20Document%20v1.0.md), particularly sections 89 through 92 and 97, for the milestone definitions.

## Proof of concept (0.1.0)

| Feature | Description | Status | Details |
| --- | --- | --- | --- |
| Phase 1 · Domain foundation | Model Run lifecycle and outcomes, Attempt and candidate identities, events, artifacts, and validated stage results. | Done | [Domain acceptance spec](spec/006-phase1-acceptance-audit/spec.md) |
| Phase 2 · Intake and frozen Run contract | Capture Markdown or GitHub Issues via local `gh`. Freeze intent, base SHA, execution settings, and verification configuration. | Done | [Intake acceptance spec](spec/018-phase2-acceptance-audit/spec.md) |
| Phase 3 · Playbook and skills | Route the canonical workflow through required stages and compose versioned Markdown guidance for each agent stage. | Done | [Methodology acceptance spec](spec/026-phase3-acceptance-audit/spec.md) |
| Phase 4 · Native-agent execution | Run fresh Codex invocations for DESIGN, PLAN, BUILD, and REVIEW with durable inputs and validated outputs. | Done | [Native execution acceptance spec](spec/030-phase4-acceptance-audit/spec.md) |
| Phase 5 · Git workspaces and candidates | Isolate work in Git worktrees, preserve the developer checkout, and record each candidate by exact commit SHA. | Done | [Git acceptance spec](spec/033-phase5-acceptance-audit/spec.md) |
| Phase 6 · Deterministic TEST | Run frozen checks against the candidate. A mandatory failure blocks REVIEW. | Done | [TEST acceptance spec](spec/036-phase6-acceptance-audit/spec.md) |
| Phase 7 · Independent REVIEW and VERIFIED | Require a positive result for every required criterion and bind verification to the tested candidate SHA. | Done | [REVIEW acceptance spec](spec/040-phase7-acceptance-audit/spec.md) |
| Phase 8 · Execution budget and evidence | Run the workflow synchronously and persist terminal reports, indexed evidence, bounded logs, timing, and provider usage when available. PACKAGE runs outside the execution budget. | Done | [Packaging acceptance spec](spec/045-phase8-acceptance-audit/spec.md) |
| Phase 9 · PoC validation | The owner accepted retained Run evidence on 2026-11-04 and waived the matched direct-Codex comparison. | Done | [PoC validation spec](spec/047-poc-validation/spec.md) |

## Local MVP (target 0.2.0)

| Feature | Description | Status | Details |
| --- | --- | --- | --- |
| Phase 10 · Background control plane | Queue Runs locally from the CLI. The service processes them one at a time and keeps running if the CLI disconnects. | Done | [Background acceptance spec](spec/057-phase10-acceptance/spec.md) |
| Phase 10 · Run history and evidence inspection | Follow progress and open past Runs and their stage evidence from the CLI or read-only browser monitor. | Done | [Run history](spec/059-saved-run-history/spec.md), [stage history](spec/060-evidence-backed-stage-history/spec.md) |
| Phase 11 · Rework and recovery | Start a linked Attempt with explicit approval. Reuse earlier stage results after validation, carry forward time already spent, record any extra time granted, and verify the new candidate by its exact SHA. | Done | [Continuation acceptance spec](spec/065-phase11-acceptance/spec.md) |
| Phase 12 · GitHub publication | Require explicit approval to publish the exact VERIFIED commit. Protect PR updates if the head has changed. | Done | [Publication spec](spec/068-github-publication/spec.md) |
| Phase 12 · GitHub collaboration evidence | Track PR status, CI results, review feedback, changes to the head, and what was merged. Let operators choose which feedback to use in an approved rework Attempt. | Done | [Collaboration spec](spec/069-github-collaboration/spec.md) |
| Run cancellation | Foreground Runs can already be interrupted and marked cancelled. Add operator cancellation through the background service and define how cancellation affects publication. | Done | [Cancellation spec](spec/070-run-cancellation/spec.md) |
| Run supersession | Let an operator replace a Run. Freeze a separate contract for the replacement and keep the original Run's evidence. | Done | [Supersession spec](spec/071-run-supersession/spec.md) |
| Web workspace and Run inbox | Build the React and shadcn/ui workspace, shared interaction patterns, and searchable Run inbox. | Done | [Workspace spec](spec/072-web-workspace/spec.md) |
| Web Run detail and evidence | Navigate Attempts and stages, inspect failed checks and artifacts, and verify which commit passed. | Done | [Run evidence spec](spec/073-web-run-evidence/spec.md) |
| Browser Run submission and control | Submit from Markdown or GitHub and use approved cancellation, supersession, rework, and recovery flows. | Done | [Browser Run operations spec](spec/074-web-run-operations/spec.md) |
| Browser GitHub delivery and MVP acceptance | Approve the exact verified commit, inspect PR evidence, and validate the packaged browser experience across every screen. | Implemented, local verification | [Browser GitHub delivery spec](spec/075-web-github-delivery/spec.md) |

## Product milestone 1 (target 1.0.0)

| Feature | Description | Status | Details |
| --- | --- | --- | --- |
| Phase 13 · Team identity and GitHub App | Add one Organization, Projects, user roles, stable actor mapping, and authorized GitHub commands. | Todo | [Identity and GitHub App spec](spec/067-team-product/spec.md#phase-13-team-identity-and-github-app) |
| Phase 14 · Remote workers and sandboxes | Assign work to capable workers via leases, run each Attempt in a fresh sandbox, and export evidence with scoped credentials. | Todo | [Worker and sandbox spec](spec/067-team-product/spec.md#phase-14-workers-and-sandboxes) |
| Phase 15 · Product persistence | Store control-plane state in PostgreSQL and persist candidate bundles and evidence with integrity and retention controls. | Todo | [Persistence spec](spec/067-team-product/spec.md#phase-15-product-persistence) |
| Phase 16 · Scheduling and governance | Set queue priorities and concurrency limits, and share capacity fairly across Projects. Define who controls methodology, agent profiles, and execution policies. | Todo | [Governance spec](spec/067-team-product/spec.md#phase-16-scheduling-and-governance) |
| Phase 17 · Headless public control plane | Expose a versioned REST API and Service Account access, with MCP, CLI, and web clients using the same contract. | Todo | [Headless control plane spec](spec/067-team-product/spec.md#phase-17-headless-public-control-plane) |
| Phase 18 · Self-hosted operations | Support portable deployment, audit, telemetry, notifications, secret resolution, backup and restore, and controlled upgrades. | Todo | [Operations spec](spec/067-team-product/spec.md#phase-18-operations) |
| Phase 19 · Analytics and learning | Report delivery outcomes and generate evidence-backed proposals for human review and activation. | Todo | [Analytics spec](spec/067-team-product/spec.md#phase-19-analytics-and-learning) |
| Product acceptance | Show that Shipyard works reliably in day-to-day use by a real engineering team across several repositories. | Todo | [Product acceptance spec](spec/067-team-product/spec.md#product-acceptance) |
