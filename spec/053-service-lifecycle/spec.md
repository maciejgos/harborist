# Specification: Phase 10 — Service lifecycle

- AC-001: Exclusive service ownership is released by the OS on exit.
- AC-002: Graceful stop drains active work and retains pending work.
- AC-003: Restart marks claims interrupted without retry or evidence mutation.
- AC-004: Serve bounded JSON HTTP over an owner-only local Unix socket.
