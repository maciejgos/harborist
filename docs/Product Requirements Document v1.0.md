# Shipyard Product Requirements Document

**Version:** 1.0  
**Status:** Discovery complete / implementation baseline  
**Date:** 25 October 2026  
**Product:** Shipyard

---

# 1. Executive Summary

Shipyard is a **headless, evidence-driven software-delivery control plane around native coding agents**.

It turns engineering intent into revision-bound, independently verified code changes while separating the authorities to:

1. execute software work;
2. verify software work;
3. publish software work;
4. approve and merge software work.

Its primary flow is:

```text
GitHub Issue or Markdown Issue
        ↓
      Shipyard
        ↓
native coding agent + Shipyard skills
        ↓
Specification
        ↓
Implementation Plan
        ↓
Implementation
        ↓
Deterministic Verification
        ↓
Independent Semantic Review
        ↓
VERIFIED candidate
        ↓
explicit publication authorization
        ↓
GitHub Pull Request
        ↓
human review / CI / merge
```

Shipyard does **not** replace Codex, Claude Code, or another capable coding agent. The coding agent retains responsibility for repository exploration, reasoning, editing, and normal implementation work.

Shipyard owns the delivery contract around that agent:

- intent;
- workflow;
- methodology;
- execution boundaries;
- verification;
- evidence;
- revision identity;
- human authority;
- publication;
- auditability;
- team governance;
- learning from outcomes.

The central product hypothesis is:

> A capable coding agent becomes materially more trustworthy for real software delivery when it operates inside a durable, revision-bound, independently verified, evidence-producing delivery system.

---

# 2. Product Vision

## 2.1 Vision

Shipyard should make autonomous or semi-autonomous software implementation **dependable enough to become normal engineering infrastructure**.

A user should be able to provide an engineering request and receive not merely generated code, but a complete delivery package answering:

- What was requested?
- What did the system decide must be true?
- How did it intend to implement it?
- What exact code revision was produced?
- Which deterministic checks passed or failed?
- Which acceptance criteria were independently verified?
- What could not be verified?
- Which model, methodology, configuration, and repository revision were used?
- Who authorized execution?
- Who authorized publication?
- What happened during human review and integration?

The system should favor **explicit uncertainty over false confidence**.

---

# 3. Product Positioning

Shipyard is not primarily:

- an AI coding assistant;
- an IDE;
- a replacement coding agent;
- a generic workflow engine;
- a CI server;
- a GitHub replacement;
- a deployment system;
- a project-management system.

Shipyard is a **software-delivery harness and control plane for native coding agents**.

The native coding agent should remain strong at what it already does well:

```text
explore repository
reason about implementation
edit code
run development-time tools
iterate locally
```

Shipyard should concentrate on what should be deterministic, durable, governed, independently inspectable, or shared across humans and agents:

```text
intent
workflow contract
methodology
permissions
budget
candidate identity
trusted verification
independent review
evidence
publication authority
audit
team governance
historical outcomes
```

---

# 4. Core Product Principles

## 4.1 Native agents remain native

Shipyard must not recreate a competing inner agent loop.

The rule is:

> **Playbooks orchestrate. Skills advise. Trusted executors enforce.**

A Shipyard playbook decides which stages must happen.

A skill provides stage-specific guidance.

The native coding agent decides how to reason and use its native tools inside the authorized stage.

---

## 4.2 Verification belongs to a revision

A verification result applies to an exact Git commit SHA.

It never applies abstractly to:

- a branch;
- a Pull Request;
- an issue;
- “the latest code.”

If code changes, verification must be performed again.

---

## 4.3 Absence of evidence is not evidence of success

Semantic review classifies every required acceptance criterion as:

```text
PASS
FAIL
UNVERIFIED
```

Only `PASS` counts positively.

Any required criterion that is `FAIL` or `UNVERIFIED` prevents `VERIFIED`.

---

## 4.4 Deterministic checks cannot be overridden semantically

Mandatory trusted checks execute before semantic review.

If any mandatory check fails:

```text
TEST_FAILED
```

Semantic review does not run.

A model may not reason its way around a failed authoritative check.

---

## 4.5 Verification, publication, approval, and merge are different authorities

Shipyard uses:

```text
IMPLEMENTED
→ VERIFIED
→ PUBLISHED
```

GitHub/team collaboration uses:

```text
PR
→ APPROVED / CHANGES_REQUESTED
→ MERGED / CLOSED
```

Therefore:

> **VERIFIED ≠ PUBLISHED ≠ HUMAN APPROVED ≠ MERGED**

---

## 4.6 Execution authority and publication authority are separate

Authorizing Shipyard to generate another Attempt does not authorize Shipyard to publish the eventual result.

Every publication requires an explicit authorization for the exact candidate being published.

---

## 4.7 Human changes to the factory are governed

Shipyard may learn from historical results and may generate concrete proposed improvements.

It may not silently modify:

- skills;
- playbooks;
- agent profiles;
- verification policies;
- execution policies.

Humans explicitly version and activate factory changes.

---

## 4.8 Historical truth is never rewritten

Later events may change current delivery state, but must not rewrite historical facts.

Examples:

```text
Candidate C was VERIFIED.
Later GitHub CI failed.

Candidate C remains historically VERIFIED.
GitHub CI is separately FAILING.
```

or:

```text
Candidate C was VERIFIED.
Human pushed commit H.

C remains VERIFIED.
Current PR head H is NOT Shipyard-verified.
```

---

## 4.9 A Run freezes its contract

The following are resolved and frozen for a Run where applicable:

- input intent;
- base Git SHA;
- playbook version;
- skill versions;
- agent execution profile;
- sandbox policy;
- execution-semantic project configuration;
- verification configuration from the base revision;
- execution budget.

Later administrative changes affect future Runs only.

---

## 4.10 Cloud portability is architectural

Shipyard must be deployable:

- locally;
- on ordinary VMs;
- on GCP;
- eventually on other infrastructure.

The core domain must depend on small capability boundaries rather than cloud-specific products.

---

# 5. Personas

## 5.1 Operator

An engineer or technical user who wants Shipyard to implement real work.

Operators may:

- submit Runs;
- reprioritize queued Runs;
- recover eligible failures;
- initiate rework;
- cancel Runs;
- create superseding Runs;
- publish VERIFIED candidates;
- inspect Runs and evidence.

Operators do not govern the methodology of the factory.

---

## 5.2 Admin

An administrator responsible for the Shipyard factory.

Admins can additionally:

- configure Projects;
- configure GitHub integration;
- configure workers;
- manage users and roles;
- manage Agent Connections;
- version and activate execution profiles;
- version and activate playbooks and skills;
- change scheduling limits;
- manage sandbox policies;
- manage infrastructure integrations.

---

## 5.3 Viewer

A read-only participant.

Viewers may inspect:

- Runs;
- Attempts;
- reports;
- evidence;
- Pull Request state;
- analytics;
- historical outcomes.

They cannot cause state-changing operations.

---

## 5.4 Service Account

A non-human principal used by:

- MCP clients;
- Lagrange;
- internal developer portals;
- automation;
- CI systems;
- custom integrations.

Service Accounts receive explicit authorization and stable audit identities.

They do not impersonate humans.

---

## 5.5 Reviewer

A human reviewing a GitHub Pull Request.

Reviewers primarily work through GitHub rather than Shipyard.

Their feedback becomes important evidence for:

- rework;
- analytics;
- factory learning.

---

# 6. Primary User Journey

## 6.1 Submission

A Run may originate from:

```text
file:./issue.md
github:acme/project#42
```

Product surfaces may include:

- CLI;
- web UI;
- REST API;
- MCP;
- GitHub `/shipyard run`.

The target implementation Project is separately identified.

The source Issue and implementation repository do not have to be the same repository.

---

## 6.2 Intake

Shipyard normalizes and freezes the source into:

```text
intent.md
```

For GitHub Issues, Product Milestone 1 uses:

- title;
- body;
- labels.

Issue comments are not authoritative intake input.

For Markdown Issues:

- Markdown body is accepted;
- optional YAML front matter may provide metadata;
- no rigid issue schema is required.

---

## 6.3 Design

A fresh native-agent invocation performs DESIGN.

It receives:

- frozen intent;
- repository context;
- Shipyard design skills.

It produces:

```text
spec.md
stage-result.json
```

Allowed stage outcomes:

```text
READY
NEEDS_CLARIFICATION
```

`spec.md` is the authoritative acceptance contract.

It defines **WHAT must be true**, not how to implement it.

---

## 6.4 Plan

A fresh native-agent invocation performs PLAN.

It receives:

- intent;
- spec;
- repository context;
- planning skills;
- remaining execution budget.

It produces:

```text
plan.md
stage-result.json
```

Allowed outcomes:

```text
READY
NEEDS_RESCOPING
```

`plan.md` is implementation guidance.

It describes **HOW Shipyard intends to implement the specification**.

It is not the correctness contract.

---

## 6.5 Build

A fresh native-agent invocation performs BUILD.

It receives:

- intent;
- spec;
- plan;
- repository state.

The agent may:

- explore;
- edit;
- run normal development checks;
- revise its implementation approach;
- update `plan.md` when material implementation deviations are discovered.

It may not silently rewrite `spec.md`.

If implementation reveals that the frozen contract cannot reasonably be satisfied without a new product decision or scope expansion, BUILD terminates as:

```text
NEEDS_CLARIFICATION
```

or:

```text
NEEDS_RESCOPING
```

When BUILD succeeds, Shipyard creates a Git candidate commit.

---

# 7. Canonical Artifact Chain

The canonical development chain is:

```text
intent.md
   ↓
spec.md
   ↓
plan.md
   ↓
candidate Git commit
   ↓
TEST evidence
   ↓
review.md
   ↓
report.md
```

Meaning:

| Artifact | Meaning |
|---|---|
| `intent.md` | Why / requested outcome |
| `spec.md` | What must be true |
| `plan.md` | How implementation is intended |
| Git candidate | What was actually implemented |
| TEST evidence | What deterministic verification proved |
| `review.md` | What independent semantic review proved |
| `report.md` | Human-facing synthesis |

The system does not require full native-agent transcripts or private reasoning.

---

# 8. Canonical Playbook

Product Milestone 1 supports exactly one canonical workflow:

```text
bounded-repository-change
```

Its logical stages are:

```text
INTAKE
→ DESIGN
→ PLAN
→ BUILD
→ TEST
→ REVIEW
→ PACKAGE
```

The organization may version the playbook:

```text
bounded-repository-change@1
bounded-repository-change@2
bounded-repository-change@3
```

but Product Milestone 1 does not become a generic multi-workflow platform.

Different work types should first be handled through:

- issue intent;
- repository context;
- skills;
- verification configuration;

rather than proliferating playbooks.

---

# 9. Skills

A Shipyard skill is a human-readable Markdown asset with small YAML front matter.

Example:

```yaml
---
id: review-change
version: 7
description: Independently assess a candidate against its specification.
---
```

A skill may bundle static:

```text
templates/
references/
```

Skills do not contain executable hooks in the first Product milestone.

Multiple skills may be composed into one native-agent invocation.

If something requires:

- independent execution;
- independent timeout;
- independent permissions;
- its own output contract;

it should be a playbook step rather than a skill.

---

# 10. Methodology Governance

## 10.1 Organization library

Shipyard ships default methodology assets.

Organizations adopt and own a governed library:

```text
Organization
├── Playbooks
└── Skills
```

Published versions are immutable.

Changing an asset creates a new version.

---

## 10.2 Activation

Only Admins may:

- create;
- activate;
- deactivate;
- roll back;

playbook and skill versions.

Operators use the active methodology.

---

## 10.3 Run freezing

Runs freeze exact methodology versions at creation.

An Admin changing the current version does not affect:

- queued Runs;
- active Runs;
- recovery Attempts;
- rework Attempts.

---

## 10.4 Project override

The Organization has a default canonical playbook version.

A Project may temporarily pin an approved organization-library version.

This supports controlled rollout.

---

## 10.5 Controlled rollout

New methodology is validated through real Project pilots:

```text
create immutable version
→ select pilot Project
→ Project override
→ observe outcomes
→ Admin promotes or rolls back
```

No shadow execution is required in Product Milestone 1.

---

# 11. Deterministic Verification

## 11.1 `shipyard.yaml`

Each target repository contains a committed:

```text
shipyard.yaml
```

Product Milestone 1 keeps this intentionally narrow.

Example:

```yaml
version: 1

checks:
  - id: tests
    command: pytest
```

It defines trusted deterministic checks.

It does not become a general project manifest.

---

## 11.2 Frozen verification configuration

Shipyard reads `shipyard.yaml` from the Run’s frozen base commit.

If BUILD modifies `shipyard.yaml`, that change does not alter how the current candidate is judged.

---

## 11.3 Configuration requirements

At least one authoritative check is required.

Missing configuration or no checks results in:

```text
CONFIGURATION_ERROR
```

before native-agent execution starts.

---

## 11.4 TEST behavior

TEST runs all configured mandatory checks.

It does not stop at the first failure.

The result should contain complete evidence for all checks.

If any mandatory check fails:

```text
TEST_FAILED
```

REVIEW does not run.

---

# 12. Semantic Review

REVIEW uses:

- a fresh native-agent invocation;
- a fresh context;
- read-only repository access;
- the exact candidate SHA;
- spec;
- test evidence.

The same provider/model may be used as BUILD, but the invocation must be independent.

REVIEW produces:

```text
review.md
stage-result.json
```

Every required acceptance criterion is classified:

```text
PASS
FAIL
UNVERIFIED
```

The candidate is `VERIFIED` only when:

```text
all mandatory TEST checks pass
AND
all required acceptance criteria == PASS
```

Any `FAIL` or `UNVERIFIED` results in:

```text
CHANGES_REQUIRED
```

---

# 13. Candidate Identity

BUILD produces a candidate Git commit before authoritative TEST.

TEST and REVIEW operate on that exact immutable SHA.

For PoC, the candidate remains reachable through a Shipyard-owned ref such as:

```text
refs/shipyard/runs/<run-id>/candidate
```

For Product, the candidate is also exported durably before the sandbox is destroyed.

---

# 14. Stage Contracts

Each native-agent stage produces:

1. a human-readable semantic artifact;
2. a small machine-readable `stage-result.json`.

Workflow state must never be inferred from prose.

The machine contract is intentionally small.

Example concepts:

```json
{
  "stage": "review",
  "status": "ready",
  "summary": {
    "pass": 8,
    "fail": 0,
    "unverified": 0
  }
}
```

Shipyard validates:

1. process success;
2. schema validity;
3. stage-specific invariants.

Invalid output results in:

```text
INVALID_STAGE_OUTPUT
```

Shipyard does not guess and does not automatically repair the result in early releases.

---

# 15. Packaging and Evidence

PACKAGE always attempts to finalize the Run.

It is outside the execution time budget.

Shipyard may fail to finish software work, but should still finish explaining what happened.

Every terminal result should have:

```text
report.md
```

and machine-readable evidence.

The report exists for:

- VERIFIED;
- NEEDS_CLARIFICATION;
- NEEDS_RESCOPING;
- TEST_FAILED;
- CHANGES_REQUIRED;
- failed execution;
- cancellation;
- supersession.

---

# 16. Execution Budget

A Run has a frozen overall execution budget.

It comes from:

- Shipyard default;
- optional explicit override such as `--timeout`.

Budget is not repository-controlled.

Stage percentages are planning targets, not rigid slices.

Unused time may roll forward.

Shipyard must reserve enough budget for verification so BUILD cannot consume the entire budget.

Queue waiting time does not count against execution budget.

If budget is exhausted:

```text
TIME_BUDGET_EXCEEDED
```

The active executor is terminated best-effort.

PACKAGE is still permitted to finalize evidence.

---

# 17. Native-Agent Execution

Shipyard defines a small internal native-agent contract.

PoC implementation:

```text
Codex
```

Product playbooks refer to:

```text
executor: native-agent
```

not to vendor-specific names.

Fresh invocations are required for:

- DESIGN;
- PLAN;
- BUILD;
- REVIEW.

No agent session continuity is assumed between stages.

The durable artifact chain is the only required communication channel between stages.

One stage equals one native-agent invocation in the initial design.

---

# 18. Agent Connection and Execution Profile

An **Agent Connection** represents authentication and connectivity to a native coding-agent provider.

An **Agent Execution Profile** represents execution semantics such as:

- model;
- effort level;
- supported native settings.

Product Milestone 1 uses one organization-wide default profile, with optional approved Project override for controlled rollout.

A Run freezes the resolved profile.

Recovery and rework remain on the same frozen profile.

Trying a materially different model/profile means creating a new Run.

---

# 19. Git and Workspace Model

## 19.1 Base selection

Default:

```text
current committed HEAD
```

Optional explicit ref:

```text
--ref main
--ref <sha>
```

The ref is resolved exactly once at Run creation.

The resulting:

```text
base_sha
```

is immutable.

---

## 19.2 Dirty developer state

Local uncommitted changes are ignored.

Shipyard operates from committed Git state in an isolated worktree or sandbox.

Developer modifications are untouched.

---

## 19.3 Isolation

Worktrees provide Git isolation.

They are not a security boundary.

Product sandboxing provides the stronger execution boundary.

---

# 20. Rework

Rework means:

> The system executed correctly, but the candidate was insufficient.

Typical trigger:

```text
CHANGES_REQUIRED
```

or later human/CI feedback on a published PR.

Rework creates a **new Attempt inside the same Run**.

It does not resume the previous agent session.

It restarts at PLAN.

A rework Attempt receives:

- frozen intent;
- frozen spec;
- previous plan;
- previous candidate;
- TEST evidence;
- REVIEW evidence;
- relevant human review feedback;
- relevant bounded GitHub CI evidence.

The spec remains fixed.

If satisfying feedback requires materially changing the spec, the same Run cannot continue.

The correct outcome becomes:

```text
NEEDS_CLARIFICATION
```

or:

```text
NEEDS_RESCOPING
```

followed by a new Run.

---

# 21. Rework Git Lineage

The first Attempt begins from the Run base:

```text
A → B
```

A rework Attempt starts from the previous candidate:

```text
A → B → C
```

Therefore a Run may have:

```text
run_base_sha: A

Attempt 1:
  start_sha: A
  candidate_sha: B

Attempt 2:
  start_sha: B
  candidate_sha: C
```

Every candidate receives fresh TEST + REVIEW.

Verification never transfers between candidates.

---

# 22. Target-Branch Drift

If the target branch advances:

```text
Shipyard: A → B → C

main:     A → X → Y
```

Shipyard does not silently rebase or merge `Y` into the existing Run.

It records drift as evidence.

A Run evolves its candidate lineage; it does not silently evolve its foundation.

Publication may still occur for exact candidate `C`.

Integration state is represented separately.

---

# 23. Recovery

Recovery means:

> Execution failed for infrastructure or probabilistic reasons, rather than because the candidate failed software verification.

An explicit human `RECOVER` action creates a fresh Attempt.

The failed native-agent session is never resumed.

Only validated durable upstream artifacts are reused.

Initially recoverable reasons include:

```text
EXECUTION_FAILED
INVALID_STAGE_OUTPUT
CREDENTIAL_UNAVAILABLE
CREDENTIAL_REJECTED
```

Not automatically recoverable:

```text
CONFIGURATION_ERROR
TIME_BUDGET_EXCEEDED
INTERNAL_ERROR
```

Recovery uses the remaining Run budget by default.

An Operator may explicitly grant additional time.

Shipyard never silently extends resources.

---

# 24. Run Lifecycle and Outcomes

Lifecycle and software outcome are distinct.

## 24.1 Lifecycle

```text
CREATED
QUEUED
RUNNING
COMPLETED
FAILED
CANCELLED
```

A `FAILED` Run may be eligible for explicit Recovery depending on its failure reason.

`CANCELLED` is terminal.

---

## 24.2 Completed outcomes

```text
VERIFIED
NEEDS_CLARIFICATION
NEEDS_RESCOPING
TEST_FAILED
CHANGES_REQUIRED
```

---

## 24.3 Failure reasons

Core reasons include:

```text
CONFIGURATION_ERROR
EXECUTION_FAILED
INVALID_STAGE_OUTPUT
TIME_BUDGET_EXCEEDED
CREDENTIAL_UNAVAILABLE
CREDENTIAL_REJECTED
INTERNAL_ERROR
```

---

## 24.4 Attention states

Additional product states may surface:

```text
RECOVERY_REQUIRED
UNSCHEDULABLE
PUBLICATION_CONFLICT
RECOVERY_DEGRADED
```

These must not be conflated with candidate verification outcomes.

---

# 25. Cancellation

Cancellation is a distinct human control-plane action.

It is not a reliability failure.

Cancellation is Run-terminal.

A cancellation records:

```text
cancelled_by
cancelled_at
reason
attempt_id
stage_at_cancellation
```

For active execution:

```text
request cancellation
→ signal worker
→ terminate executor best-effort
→ persist valid bounded evidence
→ destroy sandbox
→ finalize CANCELLED
```

If a VERIFIED candidate exists but has not yet been published, cancellation makes it no longer publishable.

The candidate remains evidence.

A cancelled Run is historically inspectable but operationally dead.

---

# 26. Superseding Runs

An Operator may explicitly create a new Run that supersedes an older Run.

Example:

```text
Run 184
  lifecycle: CANCELLED
  reason: SUPERSEDED
  superseded_by: Run 191

Run 191
  supersedes: Run 184
```

The new Run gets fresh:

- intent;
- base SHA;
- methodology;
- profile;
- budget;
- Attempts.

Old artifacts may be supplied as:

```text
historical_context: true
authoritative: false
```

Supersession preserves knowledge, not authority.

If the old Run has an open PR, Shipyard may mark/comment that it was superseded.

Shipyard does not automatically close the PR.

---

# 27. Publication

A candidate must be:

```text
VERIFIED
```

and the Run must remain operationally eligible before publication.

Publication is an explicit Operator/Admin action.

The delivery component:

1. obtains the exact candidate artifact;
2. reconstructs/imports it;
3. verifies candidate SHA;
4. obtains a short-lived GitHub write credential;
5. pushes the exact candidate;
6. creates or updates the Pull Request.

Publication must never:

- rebase;
- amend;
- squash;
- regenerate;
- otherwise modify;

the verified candidate.

---

# 28. Pull Request Evidence

A newly created PR should contain a concise evidence summary including:

- request;
- implementation summary;
- base SHA;
- candidate SHA;
- deterministic check results;
- acceptance-criterion coverage;
- independent-review result;
- known limitations;
- reference to full Shipyard evidence.

GitHub remains the primary human code-review surface.

Shipyard does not automatically merge.

---

# 29. GitHub Commands

Product Milestone 1 supports explicit GitHub commands such as:

```text
/shipyard run
/shipyard rework
/shipyard publish
```

Each command:

1. arrives through authenticated GitHub App webhook;
2. is deduplicated/idempotent;
3. resolves the GitHub actor;
4. maps that actor to a Shipyard User;
5. checks Operator/Admin authority;
6. invokes the same canonical domain API used by UI/CLI.

---

# 30. Target Project Resolution

If an Issue belongs to a repository that maps unambiguously to a Shipyard Project:

```text
/shipyard run
```

may infer the target.

For cross-repository backlog use:

```text
/shipyard run project=payments
```

If no unique target can be resolved, Shipyard refuses to guess and surfaces valid choices.

---

# 31. Human PR Feedback

Human `CHANGES_REQUESTED` does not automatically spend Shipyard resources.

An authorized user explicitly runs:

```text
/shipyard rework
```

Human comments become additional evidence for the next Attempt.

If the feedback is compatible with the frozen spec, rework proceeds.

If it materially changes the acceptance contract, same-Run rework is refused.

---

# 32. Human PR Commits

If a human extends the Shipyard candidate:

```text
A → B → H
```

where `B` was the last Shipyard candidate, `H` may become the starting SHA for an explicitly authorized rework Attempt.

It is recorded as:

```text
start_revision_origin: github_pr_head
start_revision_verified: false
previous_verified_candidate_sha: B
```

The resulting candidate must pass complete TEST + REVIEW.

---

# 33. Rewritten PR History

If a human force-pushes/rebases so the current PR head is no longer a descendant of the last Shipyard-published candidate, same-Run rework is not permitted.

Example:

```text
A → B

A → X → H
```

A new Run is required.

Human commits may extend Shipyard lineage.

They may not silently replace its foundation.

---

# 34. Publication Concurrency Control

If an Attempt began from PR head `H` and produced `C`, publication records:

```text
expected_pr_head_sha: H
```

Before updating the PR, Shipyard checks the current GitHub head.

If:

```text
current == H
```

publication may proceed.

If:

```text
current == J
```

Shipyard returns:

```text
PUBLICATION_CONFLICT
```

and pushes nothing.

Shipyard never force-pushes over human work.

---

# 35. GitHub CI

Shipyard verification and GitHub CI are separate dimensions.

Example:

```text
Shipyard verification:
VERIFIED

GitHub required CI:
FAILING
```

A later CI failure does not rewrite historical Shipyard verification.

Shipyard reads GitHub branch-protection/ruleset semantics to distinguish required checks from optional checks.

`shipyard.yaml` remains authoritative for Shipyard pre-publication verification.

GitHub remains authoritative for GitHub merge policy.

---

# 36. CI Evidence

Shipyard retains bounded CI evidence such as:

```text
check name
provider
conclusion
candidate SHA
timestamps
GitHub URL
bounded failure summary
annotations where available
```

It does not blindly copy unlimited CI logs.

Relevant CI failure evidence may become input to explicitly authorized rework.

---

# 37. Integration Readiness

Integration readiness is independent from Shipyard verification.

Example values:

```text
CLEAN
BEHIND
CONFLICTING
UNKNOWN
```

Therefore a candidate may be:

```text
VERIFIED
PUBLISHED
CONFLICTING
```

without contradiction.

---

# 38. PR Head Integrity

If Shipyard publishes candidate `C`, then a human pushes `H`:

```text
C → H
```

Shipyard shows:

```text
verified_candidate_sha: C
current_pr_head_sha: H

publication_integrity:
DIVERGED_FROM_VERIFIED_CANDIDATE
```

Historical verification remains attached to `C`.

Shipyard must never present `H` as verified.

---

# 39. Merge Observation

Shipyard observes but does not perform merge.

On merge it records:

```text
pr_number
pr_url
merged_at
merged_by
target_branch
publication_candidate_sha
merge_commit_sha
```

Deployment and release orchestration are explicitly outside Product Milestone 1.

---

# 40. Merge Provenance

Shipyard should inspect how strongly the merged result can be related to the verified candidate.

Example categories:

```text
MERGED_EXACT
MERGED_DESCENDANT
MERGED_SQUASHED
MERGED_UNKNOWN
```

The taxonomy may be refined technically, but Shipyard must not claim provenance it cannot prove.

Shipyard records provenance rather than dictating the team’s merge strategy.

---

# 41. Project Model

One canonical Shipyard Project maps to one GitHub repository.

A Project remains intentionally thin:

```text
id
organization
repository
default branch
GitHub installation
worker requirements
sandbox profile
methodology/profile overrides
enabled state
run history
```

Repository truth remains in the repository.

Shipyard does not duplicate:

- language;
- frameworks;
- architecture;
- test commands;
- repository documentation;

into a large Project manifest.

---

# 42. Repository Context

Repository-native agent instructions such as `AGENTS.md` are consumed through the native coding agent’s own behavior.

Shipyard does not build its own competing repository instruction parser or RAG subsystem in Product Milestone 1.

Shipyard records provenance such as applicable instruction file paths/hashes where practical.

PLAN declares expected change scope.

BUILD may deviate when repository reality requires it, but material deviations must be visible to REVIEW.

No hard path allowlist is required initially.

---

# 43. Organization and Identity

Product Milestone 1 supports one Organization per self-hosted deployment.

Organization remains a first-class domain concept so future SaaS can support multiple Organizations without changing ownership semantics.

Human authentication:

```text
GitHub first
OIDC/SSO later
```

Shipyard uses its own stable internal User identity.

Audit records must not rely solely on mutable GitHub usernames.

---

# 44. RBAC

Organization-wide roles:

## Admin

May govern factory and infrastructure.

## Operator

May execute and deliver work.

## Viewer

May inspect.

Project-scoped RBAC is deferred.

---

# 45. Service Accounts

Service Accounts are machine identities for the headless product.

They may use:

- REST;
- MCP;
- automation;
- external portals.

All actions are attributable:

```text
actor_type: service_account
actor_id: <stable id>
```

The product avoids generic anonymous “system” actors where a concrete machine identity exists.

---

# 46. Headless Product Architecture

Shipyard is a **headless control plane**.

First-party interfaces are replaceable clients:

```text
CLI ─────────┐
Web UI ──────┤
MCP ─────────┤
GitHub ──────┼──→ Public Shipyard Control Plane
Custom UI ───┤
Lagrange ────┤
Automation ──┘
```

Anything the first-party UI can do operationally must be possible through the supported public control-plane contract.

No state-changing capability may exist only inside the first-party UI/CLI/MCP implementation.

---

# 47. REST API

Product Milestone 1 exposes a supported, versioned REST API around domain operations.

Representative concepts include:

```text
Projects
Runs
Attempts
Evidence
Workers
Recovery
Rework
Cancellation
Publication
Configuration
```

State-changing APIs should express domain commands rather than raw database CRUD.

Example:

```text
CreateRun
CancelRun
RecoverRun
ReworkRun
PublishCandidate
```

---

# 48. MCP

The MCP server is a first-party agent-facing adapter over the canonical Shipyard control plane.

It is not a second workflow engine.

MCP access uses normal Shipyard authentication and authorization, including Service Accounts.

---

# 49. CLI

PoC CLI is synchronous.

Later CLI becomes a client of the background control plane.

Representative submission:

```text
shipyard run file:./issue.md
shipyard run github:acme/project#42
```

Optional target:

```text
--repo
```

Optional base:

```text
--ref
```

Optional budget:

```text
--timeout
```

Normal CLI output shows Shipyard workflow state and results rather than unbounded raw coding-agent chatter.

---

# 50. Web UI

MVP/Product UI provides:

- Run history;
- Run detail;
- stage timeline;
- Attempt history;
- evidence;
- reports;
- candidate identity;
- publication action;
- PR state;
- CI state;
- integration readiness;
- worker state;
- queue state;
- analytics;
- notifications.

It is not the authoritative product boundary.

---

# 51. GitHub App

Product Milestone 1 uses a GitHub App.

No PAT fallback is required in the first Product milestone.

Authorized repositories become Shipyard Projects.

GitHub credentials belong to the Organization integration, not to workers or users.

Credentials should be short-lived and purpose-scoped.

---

# 52. Credential Separation

Execution authority and publication authority use separate credentials.

Sandbox execution receives:

```text
read-only short-lived GitHub repository credential
```

It may:

- clone;
- fetch.

It may not:

- push;
- create PR;
- merge.

The delivery component outside the sandbox obtains a separate short-lived write credential only after:

```text
VERIFIED
+
explicit Publish authorization
```

No merge authority is required.

---

# 53. Sandbox Architecture

Product Milestone 1 uses Docker Sandboxes as the first isolation backend.

Workers use the standalone `sbx` CLI with sandbox compute local to the worker.
The [Phase 14 acceptance contract](../spec/081-workers-and-docker-sandboxes/spec.md)
defines this runtime choice and its isolation, ownership, and export requirements.

Shipyard depends on a small:

```text
SandboxRuntime
```

contract rather than spreading Docker-specific concepts throughout the domain.

Sandbox lifetime:

```text
one sandbox per Attempt
```

Recovery and rework receive fresh sandboxes.

No Attempt inherits a potentially corrupted environment from another Attempt.

---

# 54. Sandbox Network Policy

Product supports profiles such as:

```text
standard
restricted
```

`restricted` is recommended/default for production team usage.

`standard` exists for compatibility.

The native agent may not dynamically expand its own network authority.

---

# 55. Trusted-Local Mode

Shipyard also supports an explicit trusted-local development/evaluation mode.

This mode is:

- useful for PoC/local development;
- intentionally unsafe for hostile code;
- clearly labeled.

The same Run/Attempt/artifact semantics should remain consistent across trusted-local and sandboxed modes.

---

# 56. Worker Architecture

The Product control plane and workers are separate components.

Workers are long-running registered infrastructure.

Workers pull compatible work.

The control plane grants exactly-one leases.

Workers periodically heartbeat/renew leases.

Lease expiry means:

> execution ownership is uncertain.

It does **not** prove that execution stopped.

Shipyard must not silently reassign such work.

It becomes:

```text
RECOVERY_REQUIRED
```

for explicit operator action.

---

# 57. Worker Capabilities

Worker capabilities remain infrastructure-oriented.

Examples:

```text
architecture
sandbox runtime/version
CPU
memory
codex capability
```

Shipyard should not encode every project framework/language as scheduler metadata.

Those belong inside the repository/sandbox environment.

---

# 58. Unschedulable Work

If compatible workers exist but are busy/offline:

```text
QUEUED
```

If no registered worker satisfies the Run’s requirements:

```text
UNSCHEDULABLE
```

must be surfaced explicitly.

Queue time remains separate from execution budget.

---

# 59. Queue Priority

Priority values:

```text
HIGH
NORMAL
LOW
```

Default:

```text
NORMAL
```

Priority may be changed by an Operator/Admin while the Run remains queued.

Changes are audited.

Once execution begins, priority becomes historical metadata.

Priority does not affect execution semantics.

---

# 60. No Preemption

A HIGH Run does not interrupt a currently executing lower-priority Attempt.

HIGH means:

```text
next eligible work
```

not:

```text
terminate current work
```

Explicit cancellation remains the mechanism for stopping active work.

---

# 61. Queue Fairness

Within each priority class, Shipyard uses lightweight Project fairness.

Conceptually:

```text
payments → orders → portal → payments
```

FIFO is preserved within each Project.

Fairness is best-effort among Runs compatible with available workers.

Even HIGH work remains subject to Project rotation.

---

# 62. Priority Aging

Long-waiting Runs gain effective scheduling priority to prevent starvation.

Example:

```text
declared_priority: LOW
effective_priority: NORMAL
promotion_reason: queue_aging
```

The declared priority never changes silently.

Aging thresholds are simple Organization-wide operational policy.

---

# 63. Concurrency Limits

Admins configure simple hard maximums:

```text
organization.max_running_attempts
project.max_running_attempts
```

An Attempt may start only when both limits allow it.

These are maximums, not capacity reservations.

Unused Project capacity remains available to other Projects.

If an Admin lowers a limit below current usage:

```text
state: OVER_LIMIT
```

existing Attempts continue.

New Attempts are not admitted until usage drops below the configured maximum.

---

# 64. Persistence Architecture

Product persistence separates three concerns:

```text
Relational DB
→ workflow/control state

ArtifactStore
→ documents/evidence/logs/candidate bundles

Git/GitHub
→ published code identity and collaboration truth
```

PostgreSQL is the relational database.

The architecture does not require a generic database abstraction beyond standard PostgreSQL semantics.

---

# 65. ArtifactStore

Shipyard uses a small capability boundary:

```text
ArtifactStore
```

Potential adapters:

```text
filesystem
GCS
S3
MinIO
```

Domain entities refer to generic artifact references rather than GCS-specific fields.

For the official single-machine deployment, filesystem storage is acceptable.

MinIO is not required merely to imitate distributed storage locally.

---

# 66. Candidate Persistence

Before an Attempt is considered durably completed, the worker exports the candidate into durable storage.

Preferred representation:

```text
Git bundle / pack artifact
```

The durable record includes:

```text
candidate SHA
base SHA
artifact reference
artifact generation/version
hash
size
Attempt ID
```

Publication later:

1. downloads the candidate artifact;
2. verifies its integrity;
3. imports/reconstructs the Git commit;
4. verifies the SHA equals the previously VERIFIED candidate;
5. pushes that exact SHA.

Artifact export must succeed before sandbox destruction is treated as successful Attempt completion.

---

# 67. Artifact Retention

Retention is organization policy-based.

Long-lived:

- Run metadata;
- audit records;
- critical provenance.

Policy-managed:

- candidate bundles;
- failed candidate bundles;
- detailed logs;
- large evidence blobs.

When an artifact expires, metadata records that fact.

Expiration must not be mistaken for proof that the artifact never existed.

---

# 68. PoC Persistence

PoC is filesystem-only.

Example:

```text
~/.shipyard/runs/<run-id>/
```

Containing:

```text
run.json
events.jsonl
evidence.json
report.md
intent.md
spec.md
plan.md
review.md
logs/
```

Terminal PoC Run directories are immutable.

---

# 69. Audit

Audit events record:

## Human state-changing actions

Examples:

- submit;
- recover;
- rework;
- publish;
- cancel;
- supersede;
- reprioritize;
- methodology activation;
- role change;
- integration change;
- Agent Profile change.

## Security-sensitive machine actions

Examples:

- worker assignment;
- sandbox creation/destruction;
- credential issuance;
- artifact export;
- candidate access for publication;
- GitHub write credential issuance;
- PR publication attempt/result.

Audit logs never contain:

- secrets;
- tokens;
- private agent reasoning;
- full unbounded transcripts.

---

# 70. Operational Observability

Product exposes standard operational telemetry through:

- OpenTelemetry;
- Prometheus-compatible metrics;
- structured logs;
- health endpoints;
- readiness endpoints.

External operations platforms such as Grafana, GCP monitoring, or Datadog remain responsible for general infrastructure monitoring.

Shipyard UI shows product-operational information such as:

- queue;
- workers;
- Run states;
- stage failures;
- recovery state;
- verification;
- PR state.

---

# 71. Analytics

Built-in analytics remain small and interpretable.

## Throughput

- Runs;
- VERIFIED Runs;
- PRs published;
- PRs merged.

## Trust / quality

- TEST failure rate;
- REVIEW failure rate;
- UNVERIFIED criteria;
- VERIFIED candidates later receiving human `CHANGES_REQUESTED`;
- VERIFIED candidates later failing required CI.

## Efficiency

- time to VERIFIED;
- Attempts per Run;
- recoveries;
- reworks;
- agent usage.

## Human outcome

- approval rate;
- merge rate;
- time to merge.

Shipyard does not invent one opaque AI quality score.

---

# 72. Time, Usage, and Cost

Required:

```text
Run/stage start
Run/stage end
duration
original time budget
remaining time budget
```

Provider usage may include, when available:

```text
input tokens
output tokens
cached tokens
provider-native counters
```

Shipyard preserves a normalized small common usage model plus bounded provider-native metadata.

Monetary cost is recorded only when the provider reports an actual charge.

For subscription-backed execution with no attributable charge:

```text
cost = UNKNOWN
```

Shipyard does not maintain its own pricing table to fabricate an estimated actual cost.

---

# 73. Learning Loop

Shipyard analyzes historical evidence at two scopes:

```text
Project
Organization
```

A finding must say which scope produced it.

Example:

```text
Project finding:
payments API changes frequently trigger compatibility review comments.
```

versus:

```text
Organization finding:
backward-compatibility issues appear across five Projects.
```

Recommendations should include evidence basis such as:

```text
scope
observation
number of Runs
number of Projects
relevant outcomes
evidence sufficiency/confidence
proposed action
```

---

# 74. Factory Improvement Proposals

Shipyard may generate a concrete proposed change such as:

```text
review-change@7
→ proposed review-change@8
```

or:

```text
Recommend adding a compatibility check to shipyard.yaml.
```

The proposal is never automatically activated.

An Admin must review and explicitly create/activate the new version.

The governing rule is:

> Shipyard may learn from outcomes, but humans authorize changes to the system that judges future software.

---

# 75. Configuration Governance

Configuration is divided into two classes.

## Execution-semantic configuration

If changing a setting can change how code is produced or judged, it must be versioned/frozen.

Examples:

- playbook;
- skills;
- agent profile;
- sandbox policy;
- execution-relevant project settings.

## Operational configuration

Mutable with audit history.

Examples:

- concurrency limits;
- queue aging;
- worker administrative metadata;
- notification preferences.

---

# 76. Versioned Execution Policies

Reusable execution-semantic policy uses immutable named versions.

Example:

```text
codex-default@1
codex-default@2
codex-default@3
```

Admins may pilot new versions using approved Project overrides.

Promotion flow:

```text
create
→ pilot
→ measure
→ promote or roll back
```

Operators do not choose arbitrary policy versions per Run.

---

# 77. Secrets

Shipyard uses a small:

```text
SecretProvider
```

capability.

Possible adapters:

```text
environment
mounted file
external vault
GCP Secret Manager
```

Shipyard stores opaque secret references in normal domain state.

It does not treat PostgreSQL as the primary secret vault.

Secrets are resolved just in time.

---

# 78. Credential Rotation

A stable secret reference may resolve to a rotated underlying credential.

Example:

```text
secret_ref: agent/codex-production
```

The raw credential can change without changing Run execution policy.

Shipyard may safely record:

- secret provider;
- secret reference;
- issuance time;
- generation/version metadata where available.

It never records the secret itself.

---

# 79. Credential Failures

Credential failures are distinct:

```text
CREDENTIAL_UNAVAILABLE
CREDENTIAL_REJECTED
```

The native agent does not start when the required credential cannot be established.

The failure is recoverable after the infrastructure problem is corrected.

Shipyard does not silently switch providers or execution profiles.

---

# 80. Notifications

Product Milestone 1 supports:

```text
GitHub contextual notifications
+
Shipyard in-product notifications
```

Slack, Teams, and email are deferred.

Routine stage progress remains visible in Run history but does not create notifications by default.

Notifications focus on:

- NEEDS_CLARIFICATION;
- NEEDS_RESCOPING;
- CHANGES_REQUIRED;
- recovery required;
- VERIFIED candidate ready for publication;
- publication conflict;
- PR divergence;
- required CI failure;
- GitHub `CHANGES_REQUESTED`;
- supersession;
- cancellation.

Notifications are targeted where possible.

The underlying Run history remains shared for all authorized users.

Notifications never determine workflow correctness.

---

# 81. Backup and Restore

Shipyard defines a recovery contract but does not build a proprietary backup system.

Must be recoverable:

- PostgreSQL;
- ArtifactStore;
- Shipyard configuration;
- external secret references/configuration.

Reconstructable:

- workers;
- sandboxes;
- caches;
- transient execution state.

Operators use native backup mechanisms appropriate to their deployment environment.

---

# 82. Restore Semantics

After restore Shipyard verifies:

```text
database reachable
artifact references resolvable
artifact hashes/generations valid where available
integrations reconnect
workers re-register
```

Runs that were executing when ownership became uncertain become:

```text
RECOVERY_REQUIRED
```

Shipyard does not silently replay them.

---

# 83. Recovery-Degraded Mode

If PostgreSQL and ArtifactStore restore points are inconsistent, Shipyard may enter:

```text
RECOVERY_DEGRADED
```

Affected Runs are marked.

Publication requiring missing/unverifiable candidate evidence is blocked.

Unaffected history may remain inspectable.

Shipyard must never silently treat missing evidence as trustworthy evidence.

---

# 84. Product Upgrades

Historical Runs must remain readable across supported upgrades.

Execution contracts are explicitly versioned where required, potentially including:

```text
run_schema_version
playbook_schema_version
skill_format_version
stage_result_schema_version
artifact_manifest_version
worker_protocol_version
```

Storage may migrate.

Historical semantics may not.

---

# 85. Upgrade Procedure

First self-hosted Product uses controlled drain.

During maintenance:

```text
stop admitting new Attempts
allow active execution to reach safe durable boundary
persist outputs
upgrade control plane
workers re-register
resume queue
```

Any execution ownership that becomes uncertain becomes:

```text
RECOVERY_REQUIRED
```

rather than being silently resumed.

---

# 86. Worker Protocol Compatibility

The control plane and workers negotiate a small documented compatibility window.

Conceptually:

```text
current protocol: N
supported workers: N and N-1
```

An incompatible worker registers as:

```text
INCOMPATIBLE
```

and receives no work.

Version skew is bounded and explicit.

---

# 87. Deployment Architecture

## 87.1 Official minimum self-hosted deployment

Single-machine Docker Compose:

```text
Control Plane
PostgreSQL
ArtifactStore
Worker
Docker Sandboxes
```

This is the minimum officially supported team deployment.

---

## 87.2 Larger self-hosted deployment

Components may be distributed across ordinary VMs:

```text
Control Plane
PostgreSQL
shared ArtifactStore
multiple workers
Docker Sandboxes
```

---

## 87.3 GCP deployment

Managed adapters may include:

```text
Cloud SQL PostgreSQL
GCS ArtifactStore
Secret Manager
VM/container workers
```

These are deployment choices rather than Product domain dependencies.

---

# 88. Canonical Configuration Model

Shipyard has one canonical Product configuration model covering capabilities such as:

```text
database
artifact_store
sandbox
github
agent
worker
network policy
```

Deployment manifests differ:

```text
Docker Compose
VM automation
GCP Terraform
future Kubernetes
```

but configure the same conceptual Product capabilities.

The rule is:

> One Shipyard product, one configuration contract, multiple deployment topologies.

---

# 89. PoC Definition

## 89.1 Hypothesis

Can Shipyard technically wrap a native coding agent in a structured specification → implementation → verification process that produces stronger trust evidence than direct agent usage?

---

## 89.2 PoC scope

PoC includes:

- local CLI;
- Codex;
- exactly one canonical playbook;
- built-in Shipyard skills;
- Markdown and GitHub Issue intake;
- local `gh` authentication for GitHub issue reading;
- isolated Git worktree;
- committed `shipyard.yaml`;
- DESIGN;
- PLAN;
- BUILD;
- TEST;
- REVIEW;
- PACKAGE;
- exact candidate commit;
- filesystem persistence;
- candidate Git ref;
- time budget;
- evidence/report.

PoC does not include:

- background service;
- web UI;
- remote workers;
- Docker sandbox security;
- PostgreSQL;
- GitHub App;
- PR publication;
- multi-user auth;
- rework;
- recovery;
- team scheduling;
- SaaS.

---

## 89.3 PoC trust model

PoC is trusted-local.

Repository code and checks execute with the same level of trust a developer would normally grant them.

Network and host environment are inherited.

Shipyard makes no hostile-code isolation claim.

---

## 89.4 PoC validation

Phase 1:

```text
10–15 real bounded issues
on Shipyard itself
```

Phase 2:

```text
1–2 unrelated repositories
3–5 issues each
```

Task mix should include:

- bug;
- small feature;
- cross-cutting change;
- constrained refactor;
- tests/quality;
- API behavior;
- tooling/configuration.

---

## 89.5 PoC baseline comparison

For representative issues:

```text
Control:
Issue → direct Codex

Experiment:
same Issue/base → Shipyard → Codex
```

Compare:

- acceptance-criterion coverage;
- defect detection before human review;
- evidence completeness;
- explicit UNVERIFIED areas;
- reproducibility;
- reviewer confidence;
- candidate correctness;
- time/usage overhead.

Shipyard need not be faster.

It must not materially reduce candidate correctness.

The PoC hypothesis is trust-first.

---

# 90. MVP Definition

## 90.1 Hypothesis

Will an individual engineer repeatedly use Shipyard to turn real issues into trustworthy Pull Requests in a normal GitHub workflow?

---

## 90.2 MVP scope

MVP adds:

- local background Shipyard service;
- durable indexed Run/Attempt storage;
- asynchronous execution;
- queue;
- one active Attempt at a time initially;
- lightweight web UI;
- Run history;
- evidence inspection;
- explicit PR publication;
- GitHub PR lifecycle observation;
- recovery;
- rework;
- Attempts;
- human PR feedback;
- CI evidence;
- cancellation;
- supersession.

MVP remains substantially smaller than the first team Product.

---

## 90.3 MVP human workflow

```text
CLI/UI
→ submit Run
→ background execution
→ inspect evidence
→ VERIFIED
→ explicit Publish
→ GitHub PR
→ human review
→ optional explicit rework
```

GitHub remains the collaboration and approval surface.

---

# 91. Product Milestone 1 Definition

## 91.1 Hypothesis

Can a real engineering team depend on Shipyard as shared infrastructure for trustworthy agent-driven implementation across multiple repositories?

---

## 91.2 Product Milestone 1 scope

Adds the team-grade Product capabilities:

- self-hosted deployment;
- one Organization;
- User identities;
- RBAC;
- Service Accounts;
- GitHub App;
- canonical Projects;
- headless REST API;
- MCP;
- replaceable UI/CLI;
- PostgreSQL;
- ArtifactStore;
- candidate bundles;
- remote workers;
- worker leases;
- Docker Sandboxes;
- sandbox network policy;
- organization Agent Connection;
- versioned execution profiles;
- versioned methodology library;
- controlled factory rollouts;
- priority/fair queueing;
- concurrency limits;
- notifications;
- audit;
- operational telemetry;
- analytics;
- learning loop;
- SecretProvider;
- backup/restore contract;
- controlled upgrades;
- worker protocol compatibility.

---

# 92. Product Milestone 1 Exit Criteria

Milestone completion requires all three:

```text
1. Capability completeness
2. Operational reliability
3. Repeated real-team usage
```

---

## 92.1 Capability gate

All required Product capabilities operate without critical manual backdoors.

In particular:

- UI/CLI/MCP use the canonical control plane;
- state-changing operations use supported domain APIs;
- candidate/evidence persistence works;
- publication preserves exact candidate identity;
- team authority boundaries work.

---

## 92.2 Operational gate

Must demonstrate:

- Runs survive client/terminal disconnect;
- worker failures are safely surfaced;
- evidence remains durable;
- publication cannot silently mutate candidates;
- backup/restore drill succeeds;
- upgrade drill succeeds;
- audit works end-to-end;
- no silent evidence/candidate corruption;
- credential loss/recovery works;
- uncertain execution never silently replays.

---

## 92.3 Real-team usage gate

Target validation:

```text
≥ 1 real engineering team
≥ 3 Projects/repos
≥ 30 completed Runs
≥ 15 published PRs
multiple merged PRs
≥ 2 rework flows
≥ 2 recovery flows
≥ 1 cancellation/supersession path
multiple weeks of repeated usage
```

These are validation targets, not hard Product limits.

---

## 92.4 Retention gate

The strongest final milestone signal is:

> If Shipyard disappeared tomorrow, would the team actively want it back in its normal engineering workflow?

Supporting behavior includes:

- continued voluntary use;
- repeated Run submissions;
- PRs actually merged;
- Operators choosing Shipyard rather than direct coding-agent usage;
- reviewers using Shipyard evidence;
- teams continuing after the novelty period.

Product Milestone 1 is not complete merely because all code exists.

---

# 93. Product Metrics

## North-star trust metrics

- percentage of required criteria positively verified;
- percentage of VERIFIED PRs later receiving human `CHANGES_REQUESTED`;
- percentage of VERIFIED candidates later failing required GitHub CI;
- evidence completeness;
- candidate provenance integrity.

## Adoption

- weekly active Operators;
- Runs per active Project;
- repeat Run rate;
- percentage of Projects with recurring Shipyard usage;
- published PRs;
- merged Shipyard PRs.

## Reliability

- platform execution failure rate;
- worker-loss recovery rate;
- invalid-stage-output rate;
- publication conflicts;
- artifact export failures;
- evidence integrity failures.

## Efficiency

- median time to VERIFIED;
- median Attempts per Run;
- rework rate;
- recovery rate;
- agent usage;
- queue wait time.

---

# 94. Notifications and Human Attention

Human attention should be requested only when valuable.

Default notifications therefore emphasize:

```text
decision required
intervention required
material risk
meaningful delivery milestone
```

Routine machine stage completion remains visible without creating notification noise.

---

# 95. Explicit Product Non-Goals

Product Milestone 1 does **not** include:

- automatic merge;
- deployment orchestration;
- release orchestration;
- billing;
- SaaS multi-tenancy;
- enterprise SSO;
- project-scoped RBAC;
- arbitrary per-Run model routing;
- automatic model selection;
- automatic skill routing;
- self-modifying methodology;
- automatic rework loops;
- automatic recovery without authorization;
- arbitrary multiple playbooks;
- project-owned private Shipyard skill forks;
- generic plugin runtime;
- Slack/Teams/email notification framework;
- general-purpose workflow automation;
- Kubernetes requirement;
- full hostile multi-tenant execution guarantee;
- full enterprise scheduler;
- project capacity reservations;
- hard execution preemption;
- deployment-aware lifecycle;
- automatic PR closure;
- automatic rebasing;
- force-pushing over human work;
- silent adaptation to moving target branches.

---

# 96. Global DO NOT CHANGE Boundaries

The following are architecture-level invariants unless explicitly revisited through a future PRD:

1. **Shipyard wraps native coding agents; it does not replace their internal reasoning/tool loop.**
2. **`spec.md` is the acceptance contract; `plan.md` is implementation guidance.**
3. **BUILD cannot silently rewrite the frozen spec.**
4. **Mandatory TEST failures cannot be overridden by semantic review.**
5. **Every required acceptance criterion must positively PASS for VERIFIED.**
6. **Verification is bound to an exact candidate SHA.**
7. **Fresh agent invocations are used for independent stages.**
8. **Execution and publication authority remain separate.**
9. **Shipyard does not automatically merge.**
10. **Product Milestone 1 does not orchestrate deployments.**
11. **Runs freeze execution-semantic policy.**
12. **Human review feedback cannot silently rewrite a Run’s spec.**
13. **Rework creates a new Attempt, not a continuation of an agent session.**
14. **Recovery creates fresh execution from durable validated state.**
15. **Shipyard never silently rebases an existing Run onto a moving target branch.**
16. **Shipyard never force-pushes over collaboration state that changed after an Attempt began.**
17. **Historical verification results are not rewritten by later CI/human events.**
18. **The factory may recommend improvements but may not silently activate them.**
19. **First-party UI/CLI/MCP do not receive hidden state-changing capabilities unavailable through the supported control plane.**
20. **Workers do not hold durable Organization credentials.**
21. **Sandboxes do not receive GitHub publication authority.**
22. **Cloud-provider services may be adapters, not core domain dependencies.**
23. **Missing evidence is never treated as successful evidence.**
24. **Cancellation is Run-terminal.**
25. **Supersession does not inherit authoritative evidence from the old Run.**

---

# 97. Dependency-Ordered Implementation Plan

The implementation should proceed in dependency order rather than UI order.

## Phase 1 — Domain foundation

Build:

- Run;
- Attempt;
- lifecycle/outcome model;
- immutable IDs;
- artifact identities;
- candidate identity;
- event model;
- stage contracts.

### Acceptance

Machine tests prove:

- invalid state transitions are rejected;
- candidate verification always references a SHA;
- lifecycle and outcome are distinct;
- cancellation is terminal;
- rework/recovery create new Attempt identities.

### DO NOT CHANGE

Do not couple core entities to:

- GitHub SDK types;
- Docker types;
- GCS types;
- Codex-specific types.

---

## Phase 2 — Intake and frozen Run contract

Build:

- file issue adapter;
- GitHub issue adapter;
- intent normalization;
- base SHA resolution;
- frozen configuration snapshot;
- `intent.md`.

### Acceptance

Given the same frozen source/base/config, Run contract serialization is deterministic.

Changing the source Issue after Run creation does not mutate the Run.

---

## Phase 3 — Playbook engine and skills

Build:

- canonical playbook definition;
- stages;
- dependencies;
- executor types;
- skill composition;
- version identities.

### Acceptance

The playbook cannot skip mandatory stages.

Skills cannot independently alter workflow topology.

---

## Phase 4 — Native-agent stage execution

Build:

- `NativeAgent` interface;
- Codex adapter;
- fresh invocation semantics;
- DESIGN;
- PLAN;
- BUILD;
- REVIEW contracts.

### Acceptance

Each stage can execute independently from durable upstream artifacts.

No stage requires agent-session continuity.

---

## Phase 5 — Git workspaces and candidate creation

Build:

- base resolution;
- isolated worktree;
- candidate commit;
- candidate ref;
- dirty-checkout isolation.

### Acceptance

Local uncommitted developer files remain unchanged.

TEST can checkout/inspect the exact candidate SHA independently.

---

## Phase 6 — Deterministic TEST

Build:

- `shipyard.yaml`;
- base-revision config freezing;
- mandatory check executor;
- complete check collection.

### Acceptance

All configured checks run.

Any failed mandatory check prevents REVIEW.

A BUILD modification to `shipyard.yaml` cannot alter current Run verification.

---

## Phase 7 — REVIEW and VERIFIED

Build:

- criterion extraction/reference;
- PASS/FAIL/UNVERIFIED result;
- `review.md`;
- verification invariants.

### Acceptance

VERIFIED is mathematically impossible when:

```text
mandatory test failed
OR
required criterion != PASS
```

---

## Phase 8 — PACKAGE and evidence

Build:

- report;
- evidence index;
- bounded execution logs;
- usage;
- time budget accounting.

### Acceptance

Every terminal outcome produces a report.

PACKAGE remains available after execution budget exhaustion.

---

## Phase 9 — PoC validation

**Status: Completed — owner decision, 2026-11-04.**

The owner accepts the [retained PoC validation evidence](validation/2026-10-30-run-audit.md)
as sufficient to establish PoC success and proceed to MVP. The originally planned
matched baseline evaluation against direct Codex is waived as an exit requirement;
no comparative evaluation is claimed. Known acceptance and measurement gaps in
the audit remain follow-up work and do not reopen this phase.

---

## Phase 10 — Background control plane

**Status: Completed — 2026-11-04.**

The local service, durable filesystem queue, CLI client, web read model and
read-only browser monitor are implemented. Detached-execution acceptance and
closure validation are recorded in the [Phase 10 acceptance report](../spec/057-phase10-acceptance/report.md).

Build:

- service;
- durable Run/Attempt persistence;
- async queue;
- CLI as client;
- web read model.

### Acceptance

Closing the CLI does not stop the Run.

---

## Phase 11 — Rework and recovery

**Status: Completed — 2026-11-04.**

Explicit local rework/recovery, immutable linked Attempts, frozen upstream reuse,
cumulative remaining budgets and recorded additional-time grants are implemented.
Both background and foreground paths use fresh invocations and fresh exact-SHA
verification. See the [Phase 11 acceptance report](../spec/065-phase11-acceptance/report.md).
GitHub feedback/publication integration remains Phase 12.

Build:

- Attempts;
- rework;
- recovery;
- frozen upstream reuse rules;
- budget semantics.

### Acceptance

No failed agent session is ever resumed.

No previous candidate’s verification is inherited by another candidate.

---

## Phase 12 — GitHub publication

Build:

- explicit publish;
- exact candidate push;
- PR creation/update;
- optimistic PR-head check;
- CI/read-only lifecycle sync;
- divergence detection.

### Acceptance

Publication fails if reconstructed candidate SHA differs from VERIFIED SHA.

Publication fails without modifying GitHub if expected PR head has changed.

---

## Phase 13 — Team identity and GitHub App

Build:

- Organization;
- User;
- roles;
- GitHub App;
- Projects;
- actor mapping;
- GitHub commands.

### Acceptance

Unauthorized GitHub commenters cannot create Runs.

Every state-changing GitHub command maps to a stable Shipyard actor.

---

## Phase 14 — Workers and sandbox execution

Build:

- worker registry;
- capability matching;
- leases;
- heartbeats;
- SandboxRuntime;
- Docker Sandboxes adapter using worker-local `sbx`;
- temporary credentials;
- artifact export.

### Acceptance

Lease expiry never silently causes duplicate execution.

Attempt completion requires candidate/evidence export.

Sandbox receives no GitHub publication credential.

---

## Phase 15 — Product persistence

Build:

- PostgreSQL;
- ArtifactStore;
- candidate bundle;
- retention policy;
- artifact integrity.

### Acceptance

A sandbox can be permanently destroyed and a VERIFIED candidate can still later be reconstructed exactly for publication.

---

## Phase 16 — Scheduling and governance

Build:

- priority;
- Project fairness;
- aging;
- concurrency limits;
- operational configuration;
- methodology governance;
- execution-profile governance.

### Acceptance

One Project cannot starve another indefinitely under equal priority.

Lowering concurrency does not terminate existing Attempts.

Queued policy changes do not mutate frozen Run execution semantics.

---

## Phase 17 — Headless public product

Build:

- versioned REST API;
- Service Accounts;
- MCP adapter;
- CLI adapter;
- UI adapter.

### Acceptance

Every state-changing capability available in first-party surfaces is reachable through the supported control-plane contract.

---

## Phase 18 — Operations

Build:

- audit;
- notifications;
- telemetry;
- metrics;
- SecretProvider;
- backup/restore checks;
- recovery-degraded mode;
- controlled upgrade/drain;
- worker protocol negotiation.

### Acceptance

Backup/restore and upgrade drills are executed successfully before Product milestone exit.

---

## Phase 19 — Analytics and learning

Build:

- Product scorecard;
- project findings;
- organization findings;
- recommendation generation;
- proposed methodology/config diffs.

### Acceptance

Shipyard cannot activate its own recommendation.

Every recommendation exposes its evidence basis.

---

# 98. Machine-Verifiable Product Acceptance Invariants

The following should exist as automated system-level tests.

## AC-001 — Frozen issue input

Modify a source GitHub Issue after Run creation.

Expected:

```text
existing Run intent unchanged
```

## AC-002 — Frozen base

Move target branch after Run creation.

Expected:

```text
run.base_sha unchanged
```

## AC-003 — TEST authority

Force one mandatory check to fail.

Expected:

```text
outcome = TEST_FAILED
REVIEW never invoked
```

## AC-004 — Review completeness

Return one required criterion as UNVERIFIED.

Expected:

```text
VERIFIED impossible
outcome = CHANGES_REQUIRED
```

## AC-005 — Revision binding

Modify candidate after verification.

Expected:

```text
new SHA has no inherited verification
```

## AC-006 — Publication exactness

Tamper with candidate bundle before publication.

Expected:

```text
publication blocked
```

## AC-007 — Publication concurrency

Change PR head after Attempt start.

Expected:

```text
PUBLICATION_CONFLICT
no push
```

## AC-008 — Cancellation

Cancel a Run with an unpublished VERIFIED candidate.

Expected:

```text
Run = CANCELLED
candidate retained as evidence
candidate not publishable
```

## AC-009 — Supersession

Supersede an active Run.

Expected:

```text
old Run CANCELLED/SUPERSEDED
new Run has independent frozen contract
```

## AC-010 — Worker lease loss

Expire a worker lease.

Expected:

```text
no automatic duplicate assignment
RECOVERY_REQUIRED
```

## AC-011 — Artifact durability

Destroy sandbox after Attempt completion.

Expected:

```text
candidate can still be reconstructed from ArtifactStore
```

## AC-012 — Secret isolation

Inspect persisted domain/audit records.

Expected:

```text
no raw GitHub/Codex secret present
```

## AC-013 — Historical verification

Publish candidate and later fail GitHub required CI.

Expected:

```text
Shipyard verification remains VERIFIED
GitHub CI == FAILING
```

## AC-014 — PR divergence

Push human commit after VERIFIED publication.

Expected:

```text
current head marked unverified
historical candidate remains VERIFIED
```

## AC-015 — Headless parity

Perform every first-party UI mutation through REST.

Expected:

```text
same resulting domain behavior
```

---

# 99. Decision Register — Features 0–57

| Feature | Decision |
|---|---|
| 0 | Issue → Shipyard → agent → spec → implementation → verification → code + evidence |
| 1 | Free-form intent; design detects missing product intent |
| 2 | One canonical playbook; explicit Shipyard skills |
| 3 | `intent.md` → `spec.md` → `plan.md`; no PoC human gate |
| 4 | BUILD may adapt plan, never silently rewrite spec |
| 5 | Explicit trusted checks; all run; any mandatory failure stops REVIEW |
| 6 | Fresh independent semantic review; PASS/FAIL/UNVERIFIED |
| 7 | Evidence/report for every terminal result |
| 8 | `shipyard.yaml` verification-only; frozen from base revision |
| 9 | Small NativeAgent interface; Codex first |
| 10 | Frozen base SHA; isolated worktree |
| 11 | Frozen elastic execution budget; PACKAGE outside budget |
| 12 | Markdown artifact + small structured stage result |
| 13 | Lifecycle separated from software outcome |
| 14 | CLI first; synchronous PoC |
| 15 | PoC GitHub intake through local authenticated `gh` |
| 16 | Markdown skills with metadata; no executable hooks |
| 17 | Native repository context discovery |
| 18 | `VERIFIED`, not AI “approval” |
| 19 | Exact candidate publication; no auto merge |
| 20 | Rework = new Attempt in same Run |
| 21 | Recovery = fresh Attempt from validated durable state |
| 22 | Measured time, provider usage when available, real cost only |
| 23 | Filesystem PoC persistence; DB deferred |
| 24 | Trusted-local PoC; no false sandbox claims |
| 25 | PoC must prove engineering viability + trust value |
| 26 | MVP = repeated engineer workflow + async control plane |
| 27 | Self-hosted team Product first; SaaS later |
| 28 | Single Organization + User identity + Admin/Operator/Viewer |
| 29 | Remote workers + one fresh sandbox per Attempt |
| 30 | Capability scheduling + pull leases |
| 31 | GitHub App + one Project per repository |
| 32 | Sandbox network policy + execution/publication credential separation |
| 33 | Organization Agent Connection/Profile; frozen per Run |
| 34 | PostgreSQL + ArtifactStore + candidate bundles |
| 35 | Cloud-portable; Docker Compose minimum deployment |
| 36 | Domain audit + standard telemetry + small scorecard |
| 37 | Evidence-based learning recommendations; human activation |
| 38 | Organization methodology library; immutable versions |
| 39 | One canonical playbook; Project version override for rollout |
| 40 | Authorized `/shipyard run`; infer Project only when unambiguous |
| 41 | Explicit `/shipyard rework`; frozen spec; separate publication |
| 42 | Incremental candidate lineage; drift surfaced; integration status separate |
| 43 | GitHub CI separate from VERIFIED; bounded CI evidence |
| 44 | Observe merge; provenance strength; no deployment |
| 45 | Human PR commits may enter as unverified state; optimistic publication |
| 46 | Run-terminal cancellation |
| 47 | Explicit supersession; old artifacts historical only |
| 48 | HIGH/NORMAL/LOW; queued reprioritization; no preemption |
| 49 | Per-Project fair rotation + priority aging |
| 50 | Organization/Project concurrency hard caps |
| 51 | GitHub + in-product attention notifications |
| 52 | Version execution policy; audit operational settings |
| 53 | Headless public REST control plane + MCP + Service Accounts |
| 54 | SecretProvider; JIT credential resolution; distinct credential failures |
| 55 | Defined backup/restore contract + recovery-degraded mode |
| 56 | Versioned compatibility + controlled drain upgrades |
| 57 | Product exit requires capability, reliability, repeated team use, retention signal |

---

# 100. Final Product Thesis

Shipyard should not win by generating code more aggressively than native coding agents.

It should win by making their work **dependable**.

Its value comes from converting:

```text
"the agent says it is done"
```

into:

```text
Here is the frozen request.
Here is the acceptance contract.
Here is the implementation plan.
Here is the exact candidate revision.
Here are the authoritative checks.
Here is independent criterion-level review.
Here is what remains unverified.
Here is who authorized execution.
Here is who authorized publication.
Here is what humans and CI said afterward.
Here is the complete evidence chain.
```

That is the product.

Shipyard is therefore best understood as:

> **A headless, governed, evidence-driven software factory control plane that makes native coding-agent output trustworthy enough to become normal engineering delivery infrastructure.**