# Import and export Workspace configuration as YAML

[GitHub issue #15](https://github.com/maciejgos/shipyard/issues/15)

Operators can export a saved local Workspace as YAML, review its configuration
in the browser or CLI, and import it as a new Workspace or into an explicitly
selected existing Workspace. The file carries checkout and execution defaults
and integration references. The receiving installation supplies the local
checkout, execution settings file, and integration credentials.

## Acceptance criteria

- **AC-1 · Shared YAML contract.** Browser and CLI use the same versioned
  format, normalization, validation, and field errors. Version 1 is a single
  UTF-8 YAML mapping with `version: 1`, `name`, `repository`, `ref`,
  `timeout`, `verification_reserve`, and optional `settings` and
  `github_repository`. The timeout and reserve are integer seconds. Omitted
  or null `settings` selects `shipyard.settings.yaml` at the checkout root.
  Omitted or null `github_repository` uses existing GitHub origin discovery.
  Reject malformed YAML, multiple documents, duplicate keys, unsafe tags,
  unsupported versions, unknown fields, and values of the wrong type.
- **AC-2 · Preview and validation.** Import previews the normalized values
  and the proposed destination before an explicit save. Preview identifies
  invalid fields by name and reports document-level errors for invalid YAML.
  Validate the checkout, base ref, committed verification configuration,
  execution settings and methodology, budget, and optional GitHub repository
  using the same rules as Workspace editing. A preview reports when a
  checkout or settings path needs to be changed on this installation. Use
  absolute or home-relative paths in the import file and resolve them on the
  receiving installation. Preview leaves saved Workspaces and Runs untouched
  and launches no agent or verification commands.
- **AC-3 · Explicit save.** The operator explicitly chooses to create a
  Workspace or replace the configuration of a selected Workspace. Creating
  assigns a fresh ID. Replacing preserves the selected ID and applies the
  complete validated configuration. A matching name never selects an update
  target. Save revalidates the input against current local state and writes
  atomically through Workspace storage. A missing update target, validation
  failure, or failed write leaves saved configuration unchanged. The browser
  uses the existing same-origin write guards.
- **AC-4 · Export and round trip.** The browser offers a YAML download and the
  CLI can emit YAML for the selected saved Workspace. Export uses normalized
  saved values, including local paths and any saved GitHub repository, so
  reimport on the same installation with the same local inputs restores
  equivalent Workspace defaults. The execution settings path is a reference.
  The export includes only the fields in AC-1. Workspace IDs, settings file
  contents, credentials, environment values, and integration diagnostic output
  are excluded. Import rejects credential fields and credential-bearing
  integration URLs. Field errors omit rejected raw values and command output.
- **AC-5 · Frozen Run settings.** Workspace import and export leave repository
  files, Run contracts, and verification evidence unchanged. A future Run
  captures the saved defaults at intake. Existing Runs and their rework or
  recovery Attempts continue to use frozen settings. The root `shipyard.yaml`
  remains verification-only and is read from the exact frozen base commit.
  Workspace YAML cannot supply or override mandatory checks.

Automated checks cover browser and CLI validation parity, round-trip defaults
and references, invalid input with redacted field errors, preview without
writes, revalidation and atomic save failure, explicit update targeting, and
frozen Run behavior. Browser verification covers preview, correcting a local
path, explicitly saving the import, and downloading the saved configuration.

See [Local Workspaces](../077-local-workspaces/spec.md),
[Local GitHub integration](../078-github-integrations/spec.md), and
[Configuration](../../docs/configuration.md).
