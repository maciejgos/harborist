# Specification: Operator execution settings

- AC-001: Load version 1 YAML requiring playbook/skill source records
  (name, version, path), complete agent_profile and trusted-local sandbox_policy.
  Resolve asset paths relative to the resolved settings file; capture exact UTF-8
  bytes, declared identities and computed SHA-256 into ExecutionSnapshot.
- AC-002: Reject unsafe YAML, duplicate/non-string keys, unsupported versions,
  unknown fields, invalid domain settings and unreadable/invalid UTF-8 assets.
  SettingsError preserves the cause and source-path context without echoing content.
- AC-003: YAML cannot supply budget. An explicit application-provided budget wins;
  otherwise Harborist supplies 1800 seconds overall and 300 for verification.
- AC-004: Frozen snapshots and JSON round-trips survive deletion/editing of original
  settings and assets. Existing verification YAML semantics remain unchanged.

Extract the existing safe unique-key loader for reuse; do not introduce a new
configuration framework. Methodology content remains declarative input to Phase 3.
