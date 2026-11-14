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

## Implementation

The GitHub section displays publication receipts and saved PR observations.
The publication dialog submits the displayed full SHA and Attempt identity.
The shared publication operation validates both under the Run lock and
retains its expected-head checks. The PR refresh action records observed
checks, feedback, and merge status. Evidence selected for rework uses the
existing recorded observation and continuation request.

## Verification

The packaged browser was checked against a temporary local service with real
Git repositories and deterministic checks. Verified submission, failed-check
log viewing, rework, provider-failure recovery, and the exact-commit
publication dialog. Checked the desktop workspace and the 390 px detail
layout. The automated publication test replaces the remote boundary.
Live GitHub publication and PR observation were not exercised.
The built wheel contains the production HTML, JavaScript, and CSS.
Historical evidence was also opened with the keyboard and focus returned
to the log button after dismissing its dialog.
