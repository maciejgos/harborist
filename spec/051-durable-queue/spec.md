# Specification: Phase 10 — Durable queue

- AC-001: Persist validated versioned submissions with absolute execution locators.
- AC-002: Identical duplicates are idempotent; conflicts fail.
- AC-003: Atomic transitions under an exclusive lock claim at most once and reject corrupt data.
