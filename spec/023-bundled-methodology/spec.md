# Specification: Bundled methodology version 1

- AC-001: Include canonical playbook v1 Markdown and engineering skill v1 Markdown
  inside the installable Python package. Front matter must pass Phase 3 parsing;
  stage definitions preserve canonical topology and authority.
- AC-002: Provide load_default_methodology returning frozen playbook/skill assets
  with exact UTF-8 content and computed SHA-256, independent of caller cwd. Explicit
  labels must agree with document headers. Read/validation failures retain context.
- AC-003: Engineering applies to all four native-agent stages with no hooks. Its
  guidance preserves spec authority, focused testing, exact revision verification
  and fresh agent invocation. Default content declares no provider execution.
- AC-004: Update standalone intake example playbook/skill documents to the same
  versioned content. Existing explicit model/profile and budget boundaries remain.

No mutable registry, activation system, automatic Run migration or execution.
