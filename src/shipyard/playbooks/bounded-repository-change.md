---
id: bounded-repository-change
version: 1
stages:
- stage: intake
  executor: shipyard
  depends_on: []
  fresh_invocation: false
  read_only: false
  budgeted: true
- stage: design
  executor: native_agent
  depends_on:
  - intake
  fresh_invocation: true
  read_only: false
  budgeted: true
- stage: plan
  executor: native_agent
  depends_on:
  - design
  fresh_invocation: true
  read_only: false
  budgeted: true
- stage: build
  executor: native_agent
  depends_on:
  - plan
  fresh_invocation: true
  read_only: false
  budgeted: true
- stage: test
  executor: trusted_test
  depends_on:
  - build
  fresh_invocation: false
  read_only: false
  budgeted: true
- stage: review
  executor: native_agent
  depends_on:
  - test
  fresh_invocation: true
  read_only: true
  budgeted: true
- stage: package
  executor: shipyard
  depends_on:
  - review
  fresh_invocation: false
  read_only: false
  budgeted: false
---
# Bounded repository change — version 1

The canonical order is INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE.

- INTAKE freezes intent, base and execution settings.
- DESIGN uses a fresh native agent to establish spec.md as the acceptance contract.
- PLAN uses a fresh native agent to produce plan.md from durable upstream artifacts.
- BUILD uses a fresh native agent to implement the spec and produce a candidate commit.
- TEST is trusted Shipyard execution against the exact candidate SHA. Mandatory
  failures prevent REVIEW and route to PACKAGE.
- REVIEW uses a fresh independent native agent against that same candidate and spec.
- PACKAGE records evidence and report.md for every terminal result, outside budget.

Shipyard validates the machine-readable front matter independently of this
guidance. The routing engine retains authority over stages and executor types.
