---
id: engineering
version: 2
description: Implement and assess bounded repository changes against frozen acceptance
  criteria.
stages:
- design
- plan
- build
- review
---
# Engineering — version 2

Use spec.md as the acceptance contract. Inspect the target repository's operating
instructions before changing code. Keep changes focused on the requested outcome.

For behavior changes, write a focused failing test, implement the smallest correct
change and refactor with tests passing. Preserve domain/infrastructure boundaries.
BUILD may update plan.md but must not silently change spec.md.

DESIGN acceptance criteria describe observable product behavior and explicit
delivery requirements from the intent. Repository TDD instructions are operating
guidance: do not turn them into a historical-proof acceptance criterion unless
the intent explicitly requires that proof. Keep process expectations in a separate
non-AC section. Never silently drop an explicitly requested process requirement.

BUILD returns a bounded process_report in its structured response, separate from
diagnostic logs: checks contain phase (red or green), exact command, returncode,
and a concise output excerpt; limitations explains omissions and uncertainty.
Record only actual executions in their observed order, including unexpected
results. Use empty checks when no evidence is available; do not invent history.
Limits: 12 records, 2048 characters per command, 8192 per output excerpt, and
4096 for limitations. Do not write these records into the candidate repository.

REVIEW may receive build-process.json, attributed to this Run and Attempt. It is
agent-reported context, not a trusted check receipt or independent proof of
historical execution order. Its absence or log truncation alone does not fail
product criteria. If an explicit acceptance criterion requires independent proof
and the available evidence cannot establish it, mark it UNVERIFIED; never lower
the criterion or treat a self-report as independent proof. Trusted TEST remains
authoritative for the exact candidate, regardless of reported green checks.

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
