# Specification: Phase 4 acceptance audit

- AC-001: Map every PRD Phase 4 build item and both acceptance statements to
  implemented APIs and executable evidence. Add a cross-boundary subprocess smoke
  test for all four stages using a fake Codex executable and real Git.
- AC-002: Demonstrate independent invocations from reloaded durable artifacts,
  stage-specific sandbox flags and schema, BUILD edits and separate plan revision,
  exact-candidate REVIEW. Do not call a live provider or imply synthetic TEST
  receipts prove trusted checks ran.
- AC-003: Update README, architecture and changelog to describe actual Phase 4
  APIs, artifact envelope, supported profile arguments, failure semantics and
  remaining Phase 5+ responsibilities. Record validation and live-provider limits.
