# Implementation plan

1. Add real Git/check integration tests with a small NativeAgent fake for terminal paths.
2. Add exclusive lifecycle admission, journal replay and terminal snapshot persistence to the existing filesystem store.
3. Compose the explicit canonical flow with shared budget accounting and existing routing/verification boundaries.
4. Add synchronous CLI execution; surface PACKAGE failures, preserve partial captures and reject retries.
5. Validate and commit. No new design-pattern hierarchy is needed; existing adapters and explicit composition remain sufficient.
