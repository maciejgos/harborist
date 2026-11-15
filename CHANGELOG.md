# Changelog

For work in progress and planned milestones, see the [Shipyard roadmap](ROADMAP.md).

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
