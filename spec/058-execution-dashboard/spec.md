# Specification: Phase 10 browser execution monitor

- AC-001: `harborist web` serves a lightweight dashboard on loopback, using the existing control-plane service as its sole Run-data authority. UI browsing cannot submit, stop, retry, mutate or execute Runs.
- AC-002: Show searchable Run history, selected Run detail, delivery state, validated lifecycle/outcome, Attempt identity, verified candidate identity, timestamps and the canonical stage timeline. Persist observational per-stage updates without inferring missing stages as successful.
- AC-003: Poll for progress automatically and preserve selection/search across refresh. Loading, empty history, unavailable service, retry, unavailable lifecycle, execution failure and interrupted delivery have explicit states. Failed refresh identifies stale retained data.
- AC-004: Show report and evidence content through allowlisted read-only control-plane endpoints. Never expose arbitrary filesystem paths or inject stored content as HTML.
- AC-005: Support keyboard selection, visible focus, readable status labels, and narrow layouts. Verify desktop/mobile rendering and a real-service execution transition in a browser.
- AC-006: Document launch and migration, run the full pytest/Ruff/Pyright validation set, and commit the completed correction separately.
