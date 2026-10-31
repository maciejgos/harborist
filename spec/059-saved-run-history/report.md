# Saved Run history acceptance

The history API, browser and CLI now include saved Runs under ~/.shipyard/runs,
merged with service submissions. Historical Runs are projected read-only, with
no invented queue state, no required source checkout and no re-execution.

Validation: **886 tests passed** (90.23 seconds), Ruff clean, Pyright zero
errors/warnings, and `git diff --check` clean. Regression tests cover foreground
history/detail/report access with unchanged records and an empty queue,
deduplication, partial captures, symlink exclusion, missing roots, conflicting
UUIDs, default home discovery, ordering and terminal CLI wait behavior.

In-app browser QA used a separate empty-queue service reading the existing home
Runs directory. All **16 saved Runs** appeared: 14 completed executions and two
CREATED captures. Opened the historical 03fe0195 report and checked its VERIFIED
outcome, Attempt and exact candidate against displayed detail. Search narrowed
the list to LAG-017; selection and independent list scrolling survived refresh.
No relevant browser console errors were observed. The test service did not
submit, claim, restart or modify any historical Run. The monitor's layout uses
the existing design system; no new framework or remote access was introduced.

Historical per-stage observations remain unknown when absent. Recorded/update
file timestamps are presentation metadata, not proof of workflow progression.
Other arbitrary custom roots are not globally scanned; explicitly submitted
Runs retain their selected root. Conflicting UUIDs fail rather than mixing
verification across saved locations. Browser QA covered the in-app browser;
other browser engines were not separately tested.
