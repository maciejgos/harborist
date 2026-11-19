# Specification: Canonical playbook definition

- AC-001: Define immutable typed stage definitions and executor types for exactly
  INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE. Reuse ArtifactStage
  as the existing seven-stage identifier rather than introducing another enum.
- AC-002: INTAKE/PACKAGE are Harborist execution, DESIGN/PLAN/BUILD/REVIEW are fresh
  native-agent execution, TEST is trusted check execution. REVIEW is read-only;
  PACKAGE is outside budget. Freeze these declarations in the definition.
- AC-003: Every stage depends on its immediate predecessor; INTAKE has no dependency.
  Reject missing, repeated, reordered or additional stages, changed dependencies,
  changed executor authority and changed execution semantics. No arbitrary DAG.
- AC-004: Require canonical playbook name and explicit nonblank version. Preserve
  deterministic immutable JSON round-trips. Provide a canonical_playbook factory.

This is topology and execution metadata, not provider execution, lifecycle state,
trusted check evidence, runtime budget enforcement or verification authority.
