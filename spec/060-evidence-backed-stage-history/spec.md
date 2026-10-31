# Specification: Evidence-backed stage history

- AC-001: Historical Run timelines recover stage completion from validated native-stage manifests, trusted TEST captures and terminal PACKAGE evidence, rather than depending on service queue observations.
- AC-002: Match frozen Run/Attempt/candidate attribution. Missing or invalid captures never become successful by inference from prose, filenames or the overall VERIFIED label; expose invalid evidence as a stage-history error.
- AC-003: Preserve TEST failure, review rejection, clarification/rescoping, execution failure and cancellation. Show downstream stages skipped when the recorded terminal path establishes that they were not reached. Live service observations remain available and are not overwritten by recovered history.
- AC-004: Projection is read-only and never changes verification, runs agents/checks or rewrites historical records. Validate the reported historical Run in the browser, run full repository checks and commit the correction separately.
