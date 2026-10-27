---
id: engineering
version: 1
description: Implement and assess bounded repository changes against frozen acceptance
  criteria.
stages:
- design
- plan
- build
- review
---
# Engineering — version 1

Use spec.md as the acceptance contract. Inspect the target repository's operating
instructions before changing code. Keep changes focused on the requested outcome.

For behavior changes, write a focused failing test, implement the smallest correct
change and refactor with tests passing. Preserve domain/infrastructure boundaries.
BUILD may update plan.md but must not silently change spec.md.

Never infer verification from prose or process exit alone. Mandatory trusted checks
and independent REVIEW must evaluate the exact candidate commit. Document areas
that remain unverified. Do not depend on native-agent session continuity.

DESIGN must declare each required acceptance criterion explicitly on its own line
as `AC-001: Concrete observable requirement`, a Markdown list item in that form,
or a heading such as `## AC-001 — Concrete requirement`. Use unique AC IDs with
at least three digits and nonempty declaration text. All declared criteria are
required; fenced examples and prose references do not declare criteria.
REVIEW must assess exactly those IDs once each in structured criteria results.
Use PASS only with positive supporting evidence; use FAIL for unmet requirements
and UNVERIFIED for insufficient evidence. Explain assessments and limitations in
review.md. Human-readable claims never override mandatory TEST evidence.
