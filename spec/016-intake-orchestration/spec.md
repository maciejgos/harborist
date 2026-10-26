# Specification: Durable intake orchestration

- AC-001: create_run accepts source selector, injected GitRepository, FileRunStore,
  complete ExecutionSnapshot, optional ref (HEAD default), and optional CREATED Run.
  Otherwise generate a fresh Run. Reject non-CREATED state before external I/O.
- AC-002: Resolve base once, load verification configuration from that exact SHA,
  capture source once, compose and save the complete contract. Return RunContract.
  Do not invoke agents, execute checks, or advance lifecycle state.
- AC-003: Dirty checkout configuration and later branch advancement cannot change
  the chosen verification inputs. Explicit historical refs are honored without
  touching developer index/working files.
- AC-004: Saved file/GitHub captures reload without original source availability.
  Later Issue edits and source deletion cannot mutate them. Equivalent frozen
  inputs including identities serialize deterministically through storage.
- AC-005: Invalid configuration/source/storage errors propagate through existing
  typed boundaries. Invalid configuration publishes no complete capture.

Capture failures before publication raise errors; later execution-outcome/report
persistence is outside this CREATED-only use case. No new protocols or executor.
