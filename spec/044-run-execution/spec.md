# Specification: Synchronous Run execution and finalization

- AC-001: Execute a frozen CREATED capture once through fresh DESIGN, PLAN, BUILD, exact Git publication, trusted TEST and independent REVIEW using existing boundaries and a single shared budget.
- AC-002: Validated early outcomes, failed TEST, failed review, invalid output, executor failures, cancellation and budget exhaustion map to explicit terminal Run records. Failed TEST never invokes REVIEW. PACKAGE is attempted for every terminal exit outside the budget.
- AC-003: Persist lifecycle snapshots/events and stage timing, preserve frozen artifacts and terminal directories, and expose synchronous execution through the CLI without background infrastructure or recovery.
