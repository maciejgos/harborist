# Specification: Versioned methodology documents

- AC-001: Parse only supplied frozen MethodologyAsset content; no files, current
  settings or external tools. Revalidate the asset digest. Require leading YAML
  front matter bounded by --- lines and a nonblank Markdown guidance body.
- AC-002: Playbook metadata requires id, version and complete canonical stage
  definitions. Parse through PlaybookDefinition. Header id/version must match the
  frozen asset's declared name/version.
- AC-003: Skill metadata requires id, version, description and a nonempty unique
  stages list scoped to DESIGN/PLAN/BUILD/REVIEW. Reject executor, dependency,
  topology, hook and other unknown metadata. Preserve guidance as opaque Markdown.
- AC-004: Versions accept explicit nonblank string labels or positive integer
  labels normalized to strings. Reject boolean/zero/negative versions. Use safe
  unique-key YAML; malformed input raises MethodologyError retaining its cause.
- AC-005: Parsed immutable documents expose identity (kind/name/version/SHA-256),
  metadata and exact body. Same labels with changed bytes have different identity.
  Do not infer executable meaning from prose or consult current methodology files.

No mutable library registry, activation/administration system, static bundle file
loading or executable hooks. Those are not needed by the current inline Markdown
PoC. Existing Phase 2 snapshots stay readable as captures; engine compilation of
legacy plain Markdown will require explicit front-matter migration in a later slice.
