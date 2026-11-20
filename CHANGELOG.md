# Changelog

For work in progress and planned milestones, see the [Harborist roadmap](ROADMAP.md).

## 0.2.0 (Local MVP)

- Queue Runs in a local background service and use the CLI or browser workspace
  to submit requests, follow progress, and inspect saved Attempts and evidence.
- Cancel or supersede Runs and explicitly start rework or recovery Attempts.
- Approve the exact verified commit for GitHub publication and inspect the
  resulting pull request, checks, and review feedback.
- Save repository defaults in local Workspaces and diagnose GitHub and Codex
  readiness before submitting a Run.
- Use Docker Compose to start the service and browser workspace. With Docker
  Sandboxes selected, run agent stages and mandatory checks in fresh VMs.
  The current installer requires Apple silicon macOS and Docker Sandboxes
  0.54.x. See the [Docker quickstart](docs/quickstart.md).

## 0.1.0 (Proof of concept)

- Track the Run lifecycle, Attempts, and candidates, with events and artifacts
  that can be inspected after execution.
- Take a request from a Markdown file or a GitHub issue and freeze the Run's
  intent, base commit, execution settings, and required checks.
- Run DESIGN, PLAN, BUILD, and REVIEW in fresh Codex invocations using versioned
  playbook guidance and validated stage results.
- Build in a separate Git worktree so the developer's checkout stays intact.
  Record each candidate by its exact commit SHA.
- Run mandatory checks against that commit. A failed check blocks REVIEW.
  Verification requires an independent review that passes every required criterion.
- Run the workflow synchronously with a shared execution budget and time reserved
  for verification. PACKAGE runs outside that budget and saves a terminal report
  and evidence, including bounded logs, stage timings, and provider usage when
  available.
- Reject index flags that can hide tracked edits during exact-revision checks.
  Validate acceptance criteria before PLAN and keep diagnostic output when an
  agent returns missing, oversized, or invalid output.
