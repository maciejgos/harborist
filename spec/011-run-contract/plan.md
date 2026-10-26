# Plan: Minimal frozen Run contract

1. Record intent and acceptance criteria before code.
2. Add focused domain tests and observe the missing-contract failure.
3. Implement a frozen RunContract record with an after-validator for ownership and
   exact base consistency; export it from shipyard.domain. Use composition and
   existing Pydantic APIs without new factories, protocols, or infrastructure.
4. Verify deterministic compact JSON, validated round-trips, mismatch rejection,
   and representative immutability/extra-field behavior. Avoid repeating nested
   model validation matrices or Git/filesystem integration checks.
5. Update README and architecture documentation with composition and limitations.
6. Run focused tests, then uv run pytest, uv run ruff check ., and uv run pyright.
   A writable UV_CACHE_DIR override is allowed.

Acceptance mapping: composition covers AC-001; mismatched Run/base inputs through
construction and JSON cover AC-002; immutability/extra-field checks cover AC-003;
equivalent reordered mappings and round-trips cover AC-004. Review domain imports,
unchanged Run behavior, and documentation for AC-005/006.
