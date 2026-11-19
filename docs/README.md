# Shipyard documentation

## Current PoC

- [Project overview and quick start](../README.md)
- [Architecture](../ARCHITECTURE.md): invariants, workflow, artifacts and boundaries.
- [Usage](usage.md): commands, capture, execution, output and candidate application.
- [Configuration](configuration.md): mandatory checks, operator settings and budgets.
- [Storage and recovery](storage-and-recovery.md): layout, workspaces, locators and persistence guarantees.
- [Methodology](methodology.md): playbooks, skills, composition and routing.
- [Developer reference](developer-reference.md): Python APIs and module implementation contracts.
- [Working instructions](../AGENTS.md) and [changelog](../CHANGELOG.md).

## Product planning and validation

The current architecture describes the PoC. Future product requirements live in
[Product Requirements Document v1.0](Product%20Requirements%20Document%20v1.0.md).

- [Phase 14 workers and Docker Sandboxes specification](../spec/081-workers-and-docker-sandboxes/spec.md)
  ([issue #44](https://github.com/maciejgos/shipyard/issues/44)); remote workers remain planned.
- [Local Docker Sandboxes and app policy editing](../spec/082-local-docker-sandboxes/spec.md).
- [Real-run audit, 2026-10-30](validation/2026-10-30-run-audit.md)
- [Phase 1 acceptance audit](../spec/006-phase1-acceptance-audit/report.md)
- [Phase 2 acceptance audit](../spec/018-phase2-acceptance-audit/report.md)
- [Phase 3 acceptance audit](../spec/026-phase3-acceptance-audit/report.md)
- [Phase 4 acceptance audit](../spec/030-phase4-acceptance-audit/report.md)
- [Phase 5 acceptance audit](../spec/033-phase5-acceptance-audit/report.md)
- [Phase 6 acceptance audit](../spec/036-phase6-acceptance-audit/report.md)
- [Phase 7 acceptance audit](../spec/040-phase7-acceptance-audit/report.md)
- [Phase 8 acceptance audit](../spec/045-phase8-acceptance-audit/report.md)

Historical acceptance contracts, plans and audits remain in [spec/](../spec/).
Packaged playbooks and skills remain runtime resources under `src/shipyard/`.

- [Background service and CLI migration](background-control-plane.md)
