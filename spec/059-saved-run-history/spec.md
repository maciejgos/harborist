# Specification: Complete local Run history

- AC-001: Run listing includes all UUID Run directories under ~/.shipyard/runs, plus service submissions, deduplicated by matching identity/location. Historical foreground Runs require no queue record, source checkout or execution-context locator.
- AC-002: Detail and allowlisted report/evidence reads work for historical Runs. Discovery is read-only and never submits, claims, repairs, resumes or mutates saved Runs.
- AC-003: Preserve validated lifecycle/outcome, Attempt and exact verified candidate attribution. Historical records have no fabricated delivery state or per-stage success. Corrupt/partial Run captures remain visibly unavailable without hiding healthy Runs.
- AC-004: Order history consistently by recorded/submission time. Missing roots and unrelated files are harmless; symlink Run directories are excluded. Conflicting UUIDs in different roots fail explicitly rather than mixing evidence.
- AC-005: Browser history, search and selection handle historical Runs and available artifacts. CLI status --wait returns for an already terminal historical Run. Validate regressions, browser behavior and full pytest/Ruff/Pyright, then commit.
