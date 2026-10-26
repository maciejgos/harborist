# Specification: Frozen verification configuration

## Acceptance criteria

- **AC-001 — Committed-file reading:** GitRepository.read_file_at_commit requires
  a full GitCommitSha identifying an actual commit and a repository-root-relative
  path. Return blob bytes via system Git without consulting the index/worktree.
  Reject symbolic refs, missing files, non-blob targets, and tag SHAs that peel to
  another identity. GitReadError(ValueError) provides commit/path context and
  preserves underlying causes. Preserve existing resolution behavior and environment
  isolation; use a small private adapter helper for shared subprocess handling.
- **AC-002 — Narrow schema:** VerificationCheck requires strict-string id and
  command. IDs are nonempty, have no surrounding whitespace, and are unique in a
  config. Commands must contain non-whitespace text and retain their exact values.
  VerificationConfig requires strict integer version 1 and a nonempty immutable
  checks tuple preserving order. All checks are mandatory. Reject booleans/string
  versions, unknown fields, and unsupported mandatory/timeout/cwd options.
- **AC-003 — Safe parsing:** parse_verification_config accepts bytes, strictly
  decodes UTF-8, safely loads YAML with duplicate mapping key rejection and no
  custom object constructors, then validates VerificationConfig. Reject malformed,
  empty, or schema-invalid documents. YAML details stay outside the domain.
- **AC-004 — Snapshot:** VerificationConfigSnapshot contains base_sha,
  source_sha256, and config. Reuse existing SHA constraints. All models are frozen,
  forbid extra fields, and preserve valid state through JSON round-trips. Retain
  neither source text nor generated IDs/timestamps.
- **AC-005 — Base-only loading:** load_verification_config takes repository and
  base_sha, reads the fixed root path shipyard.yaml only at that exact commit,
  calculates SHA-256 of original bytes, and returns the snapshot. Do not resolve
  HEAD. Staged/unstaged edits and later commits cannot alter existing snapshots;
  repeated loading of the same base serializes identically.
- **AC-006 — Failure boundary:** Export VerificationConfigError(ValueError) for
  read, decoding, YAML, and configuration-validation failures, retaining causes
  and source context. Direct domain construction raises Pydantic validation errors.
  Add no agent execution or Run outcome mapping; missing/invalid configuration
  fails before callers can proceed to future execution.
- **AC-007 — Interfaces and documentation:** Export models through shipyard.domain,
  GitReadError through shipyard.git, and parsing/loading/error APIs through
  shipyard.verification. Add PyYAML, update the lockfile, and provide type stubs
  if required by strict Pyright. Document the schema/API and implemented capability
  in README/ARCHITECTURE.md. Preserve previous behavior and specifications.

## Completion and exclusions

Callers receive validated settings bound to an exact committed base, independently
of mutable checkout state. The digest identifies source bytes, not verification
success. Defer execution, shell semantics, optional checks, config persistence,
agent invocation, outcome selection, and complete Run contract integration. This
does not complete Phase 2 or implement TEST.

Implementation may revise plan.md; acceptance changes must be explicit.
