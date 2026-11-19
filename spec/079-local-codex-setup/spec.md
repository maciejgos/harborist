# Local Codex setup and diagnostics

[GitHub issue #14](https://github.com/maciejgos/harborist/issues/14)

Operators can check whether the local Codex CLI is available and choose
the model and reasoning effort that future Runs will use.

## Acceptance criteria

- **AC-1 · Readiness.** Integrations provides an on-demand Codex login check in
  the background service environment. `harborist agent check` uses the invoking
  terminal's environment. Both use the Codex adapter and distinguish missing
  CLI, unavailable credentials, failed checks, and a reported login. The check
  discards Codex output and does not invoke model execution.
- **AC-2 · Profile validation.** Show the configured model and reasoning effort,
  or explain that the settings file is unreadable or the profile is invalid.
  Reuse the adapter's validation for diagnostics, intake, and execution.
  Diagnostic responses omit raw command output and invalid input values.
  `agent check --json` returns separate connection and profile results. The
  command exits with status 1 when either check needs attention.
- **AC-3 · Profile setup.** The operator can set a model and select the Codex
  default or one of `minimal`, `low`, `medium`, `high`, and `xhigh` in
  Integrations or with `harborist agent configure`. The browser uses the saved
  Workspace's settings path or its checkout-root default. The CLI uses the
  checkout-root default or an explicit `--settings` path. Saving validates and
  atomically replaces the existing YAML, retaining other settings values.
  Re-serialization can change formatting and remove comments.
- **AC-4 · Frozen execution.** Intake captures the selected profile in the
  Run contract. Changes take effect on future captures. An existing Run and
  its rework or recovery Attempts continue to use the frozen profile.
- **AC-5 · Browser boundary.** Profile edits use the local service through
  the existing same-origin write checks. The browser identifies the saved
  Workspace by ID and cannot supply a file path in a profile update.

Automated checks cover profile freezing, Workspace path selection, diagnostics
without credentials, redaction, and browser request guards. Browser verification
covers saving and reloading the profile, credential diagnostics, and profile
controls at a mobile viewport.

See [local Codex setup](../../docs/usage.md#set-up-local-codex).
