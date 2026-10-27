# Specification: PACKAGE evidence

- AC-001: Every validated terminal Run lifecycle and outcome can produce report.md and evidence.json with exact Run/contract/candidate identity, timing, usage, checks, review coverage and explicit missing evidence.
- AC-002: Index durable files by relative path, byte length and SHA-256; refuse symlinks and foreign identities. PACKAGE is deterministic, Shipyard-controlled and has no budget admission check.
- AC-003: Publish into a create-only package directory with evidence.json last; retain partial failures, reject overwrites, and never grant verification from packaging or prose.
