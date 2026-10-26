# Specification: Intake and inspection CLI

- AC-001: Install shipyard entry point using Typer, as selected by architecture;
  support python -m shipyard. Provide intake SOURCE with required --settings,
  --repo (current directory default), --ref (HEAD), --runs-dir (~/.shipyard/runs),
  --timeout (1800 seconds) and --verification-reserve (300 seconds).
- AC-002: Validate budget input and call the existing settings loader/use case.
  Print complete machine-readable contract JSON. Expected capture/config/storage
  errors produce nonzero status and an error on stderr without traceback.
- AC-003: inspect UUID --runs-dir validates stored records and prints the same
  complete contract JSON without source/settings/Git availability.
- AC-004: Make CREATED-only intake explicit in help/docs. Do not expose a run
  command implying agent/check execution. No lifecycle/outcome changes.
- AC-005: Supply readable canonical playbook/skill and operator-settings examples,
  an example issue and Shipyard's own committed verification configuration. CLI
  round-trip and failure tests pass; dependencies and lockfile stay synchronized.

These methodology examples are frozen Phase 2 inputs. Runtime interpretation,
provider/model availability and command construction remain later-phase concerns.
