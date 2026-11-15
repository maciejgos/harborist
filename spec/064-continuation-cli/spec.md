# Specification: Explicit continuation commands

- AC-001: Provide rework and recover CLI commands with Run context resolution, bounded feedback, optional additional seconds and explicit foreground compatibility. Default submission uses the existing serial service, preserving the read-only browser.
- AC-002: Queue continuation requests with expected predecessor identity; duplicate delivery is idempotent, stale requests fail, interrupted claims never retry automatically. Report latest attempt and retained evidence paths without claiming queue acceptance is verification.
- AC-003: Normal inspection, history and candidate application resolve latest attempt evidence and retain exact-SHA validation. Historical attempt files remain accessible on disk.
