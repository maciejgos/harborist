# Workflow and verification

A **Run** captures one request and its execution inputs. An **Attempt** is one
execution of that Run. Rework and recovery create new Attempts and keep
earlier evidence available. A **candidate** is a Git commit produced by BUILD.

## The seven stages

| Stage | What happens |
| --- | --- |
| INTAKE | Capture the request, Git base revision, mandatory checks, execution budget, and agent guidance. |
| DESIGN | Define the acceptance criteria in `spec.md`. |
| PLAN | Turn the acceptance criteria into an implementation plan. |
| BUILD | Implement the change and produce a candidate commit. BUILD may update the plan and must preserve the acceptance contract. |
| TEST | Run every mandatory check from the frozen repository configuration against the candidate. A failed check blocks REVIEW. |
| REVIEW | Independently evaluate the exact candidate commit against the acceptance criteria and verification evidence. |
| PACKAGE | Preserve the outcome, artifacts, and evidence index, including available evidence when execution ends early and packaging can run. |

DESIGN, PLAN, BUILD, and REVIEW each start a fresh native-agent invocation.
Harborist runs TEST and PACKAGE itself. A stage advances through validated
structured results. Agent commentary is diagnostic context.

## What VERIFIED means

`VERIFIED` ties the recorded acceptance review and mandatory checks to a
single candidate SHA. If the code changes, the new commit needs its own
verification. A later Attempt runs fresh checks and review even when it
inherits the frozen specification.

Read the [Run evidence](usage.md#inspect-results-and-evidence) before choosing
whether to [apply the candidate](usage.md#apply-a-verified-candidate) or [publish
it to GitHub](usage.md#publish-a-verified-candidate-to-github).

If BUILD reports its development checks, Harborist saves them as
`build/build-process.json` for REVIEW. These are agent-reported observations.
The trusted mandatory check results are in the TEST artifacts.

## Playbooks and skills

The playbook defines stage order and executor responsibilities. Skills provide
guidance to selected agent stages in configuration order. The bundled
engineering skill applies to DESIGN, PLAN, BUILD, and REVIEW.

Intake captures the exact bytes of each methodology document with its identity
and SHA-256 digest. A file edit affects future Runs. Use the saved capture to
inspect the instructions a particular stage received:

```bash
harborist methodology RUN_ID --stage build
```

The supported stage selectors are `design`, `plan`, `build`, and `review`.
See [execution settings](configuration.md#operator-execution-settings) to select
playbook and skill files, or the [developer reference](developer-reference.md)
for the parsing and execution interfaces.
