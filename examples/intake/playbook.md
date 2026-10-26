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

This document is a Phase 2 frozen input. The Phase 3 engine will define and validate
machine-readable stage dependencies, executor types and skill composition.
