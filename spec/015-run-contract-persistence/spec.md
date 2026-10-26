# Specification: Complete Run capture persistence

- AC-001: FileRunStore accepts an explicit Runs root and a validated complete
  RunContract. Save run.json in CREATED, intent.md, intent.json and contract.json
  under the contract Run UUID. Publish contract.json last as completion marker.
- AC-002: Reserve the directory exclusively; existing or partial directories are
  never overwritten, including identical contracts. Report RunAlreadyExistsError.
- AC-003: Load without consulting source files, Git or settings. Validate complete
  contract, Run state, requested ownership, standalone intent integrity and exact
  agreement between intent records. Missing/invalid/disagreeing records fail.
- AC-004: RunPersistenceError retains underlying read/write/validation causes.
  Failed writes retain partial evidence; subsequent loads fail and saves reject
  the directory. Root I/O failures remain distinct from an existing Run directory.
- AC-005: Preserve exact values, identities and deterministic contract bytes across
  round-trips. Standalone FileIntentStore remains available and unchanged.

This is CREATED-only capture persistence, not general lifecycle persistence.
No repair, overwrite, multi-file atomicity or power-loss durability is promised.
