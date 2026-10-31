# Execution dashboard acceptance — 2026-10-31

The browser monitor corrects the initial Phase 10 delivery, which exposed JSON
without a visible UI. `shipyard web` is a separate loopback-only, read-only
adapter over the canonical Unix-socket service. It adds no execution authority.

## Validation

- Full pytest: **880 passed**, 87.97 seconds.
- Ruff: clean. Pyright: zero errors/warnings. `git diff --check`: clean.
- Focused tests initially failed for the missing dashboard/stage-history feature,
  then passed after implementation. Tests cover per-stage persistence, terminal
  artifact allowlisting, symlink rejection, static UI delivery, service absence,
  rejected mutations and Host validation on a real loopback HTTP server.

## Browser verification

Used the built-in in-app browser against the real local web adapter and execution
service. Test Runs used real Git, trusted checks and packaging; only native-agent
responses were synthetic. No live paid agent call was needed.

| Check | Result |
| --- | --- |
| Correct URL/title, meaningful content, no error overlay | PASS |
| Desktop layout and 390×844 narrow viewport | PASS; no horizontal overflow |
| Relevant console errors during successful use | None |
| Run selection, search and no-match state | PASS |
| Keyboard Tab/Enter selection and report-dialog focus return | PASS |
| Automatic TEST → REVIEW → PACKAGE → VERIFIED transition | PASS |
| Candidate SHA, outcome and report viewing | PASS |
| Empty history and initially unavailable service | PASS |
| Disconnect warning, retained stale data, reconnect/retry | PASS; selected Run and search retained |

The visual implementation follows the generated white/teal two-pane concept:
Run-history rail, seven-stage timeline, execution details, evidence and current
activity. Screenshots were inspected at desktop and mobile sizes. UI text and
stored artifact content render as text, never injected HTML.

## Limits

The monitor shows submissions in the selected service control directory, not an
import of every historical foreground Run. Older queue records lacking per-stage
observations display Not recorded; missing stages never imply success. INTAKE
completion reflects a validated capture. Reports/evidence are plain-text viewers
bounded to 2 MiB. The verified candidate field is present only when the validated
Run has a verification record. This is a local monitor, not team/remote access,
publication, recovery or cancellation infrastructure. Browser QA used the in-app
browser; other browser engines were not separately tested.
