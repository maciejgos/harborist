# Evidence-backed timeline acceptance

The reported Run 03fe0195 has durable stage captures; the dashboard previously
ignored them and displayed only queue observations. A read-only projection now
uses the native-stage manifests, trusted TEST capture and PACKAGE evidence to
recover its complete timeline without agents, checks or historical writes.

Stage attribution is reconciled with frozen Run/Attempt and exact candidate
records. Native completion, trusted TEST failure, review rejection,
clarification/rescoping and recorded terminal failure/cancellation paths remain
distinct. Downstream skips follow the recorded terminal path; missing or invalid
captures do not become successful because the Run is VERIFIED. Queue observations
remain available and take precedence. The projection never grants verification.

Validation: **894 tests passed** (92.70 seconds), Ruff clean, Pyright zero
errors/warnings, and `git diff --check` clean.

## Regression evidence

Tests exercise real Git/check execution with synthetic native-agent responses:
VERIFIED, TEST_FAILED, CHANGES_REQUIRED, clarification, provider failure and
cancellation; downstream skips; unchanged terminal files; foreign/missing stage
manifests; and a PACKAGE record for a different candidate. Each negative history
case leaves validated Run state intact and exposes a history diagnostic.

## Browser verification

The built-in browser showed the exact reported Run with INTAKE, DESIGN, PLAN,
BUILD, TEST, REVIEW and PACKAGE all Completed. LAG-018 showed REVIEW Failed,
PACKAGE Completed and its original CHANGES_REQUIRED outcome. No relevant browser
console errors were observed. The temporary verification service had an empty
queue and read existing home Run records; no historical Run was restarted or
changed. Other browser engines were not separately tested.

## Limits

This reconstructs presentation from attributed saved records. It does not rerun
TEST, re-assess acceptance or replace explicit apply's evidence integrity checks.
Missing captures remain unknown, and malformed captures have explicit errors.
