# Browser GitHub delivery

The operator can approve publication of a verified candidate and track the
resulting pull request from the Run detail page.

## Acceptance criteria

- Publication approval identifies the Run, eligible Attempt, exact verified
  commit SHA, destination repository and branch, and existing PR when known.
- Revalidate publication eligibility and the approved SHA when executing the
  action. Show stale approvals and branch-head conflicts with refreshed state.
- Show publication receipts and observed PR status, head SHA, CI checks,
  feedback, and merge result when available. Present GitHub observations
  alongside the Shipyard verification for the exact candidate.
- Allow eligible GitHub feedback to be selected for an explicitly approved
  rework Attempt.
- Validate the packaged experience from submission through verified
  publication and PR inspection. Review every shipped screen and dialog
  against the workspace design criteria in specification 072 on desktop
  and narrow viewports, including keyboard interaction and failure states.
