# Specification: Saved methodology preview CLI

- AC-001: Add harborist methodology UUID --runs-dir ROOT. Load and validate the saved
  capture, compile only its frozen assets and print JSON containing playbook
  identity/definition/guidance plus skill identity/metadata/guidance.
- AC-002: Optional --stage selects composed guidance for DESIGN/PLAN/BUILD/REVIEW,
  preserving configured order and exact bodies. Harborist-owned stages are rejected
  as in the composition boundary. No stage execution or lifecycle changes.
- AC-003: Expected compile/load failures return nonzero with stderr JSON and no
  traceback. Legacy captures remain inspectable through the existing inspect
  command; methodology preview reports compilation failure without upgrading them.
- AC-004: Preview works after source/settings/methodology files disappear and
  never changes saved contract bytes. Provide usage and distinguish future runtime
  validation from already-implemented Phase 3 methodology validation.
