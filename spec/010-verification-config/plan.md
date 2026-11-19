# Plan: Frozen verification configuration

## Implementation sequence

1. Record intent/specification before code. Add PyYAML plus development typing
   support and sync/lock dependencies.
2. Write focused parser/model tests and confirm failure; implement frozen models
   and a SafeLoader subclass that rejects duplicate keys. Refactor with tests green.
3. Extend existing temporary Git tests for committed blob reading and confirm
   failures. Add GitReadError and read_file_at_commit, sharing environment/process
   execution through a private helper; retain public resolve_base semantics.
4. Add configuration-loading integration tests using existing Git fixtures and
   confirm failures. Implement exact-base loading and source-byte hashing.
5. Update documentation and run all required validation.

## Interfaces and data flow

Domain: VerificationCheck(id, command), VerificationConfig(version, checks), and
VerificationConfigSnapshot(base_sha, source_sha256, config). Use frozen Pydantic
models with forbidden extras, strict scalar validation, ordered tuples, and unique
IDs. The domain imports no YAML or Git adapter types.

Git: validate a full SHA, require git --no-replace-objects cat-file -t <sha> to
identify an actual commit, then read the blob with replacement handling disabled.
A regression test showed Git replacement refs otherwise substitute different
configuration under the same requested SHA. This approach preserves normal
resolve_base behavior while reading the original immutable commit object. A
symbolic ref is invalid input; a tag SHA cannot silently become another commit.
Paths are root-relative POSIX paths; reject
empty, absolute, and parent-traversal paths, and remove leading ./ components before
constructing the object expression. This also avoids Git's cwd-relative ./ syntax.
Use the existing isolated environment for both operations. Wrap read failures with
GitReadError; leave invalid caller SHA validation as a Pydantic error.

Verification: parse_verification_config(source: bytes) returns VerificationConfig.
Decode UTF-8, use safe YAML constructors, reject duplicate mapping keys, and
validate domain settings. load_verification_config(*, repository, base_sha) requests
harborist.yaml at the supplied base, parses it, and constructs a snapshot using the
source-byte SHA-256. Errors retain original causes and identify harborist.yaml/base
context without including source contents. No ref refresh or command execution.

## Verification mapping

- AC-001: exact file bytes, nested repository path, missing/tree targets, full-SHA
  enforcement, and tag-object rejection using existing temporary Git fixtures.
- AC-002/003: supported schema, unknown/missing/wrong fields, unsupported versions,
  empty checks, duplicate IDs/keys, blank commands, bad YAML/UTF-8, unsafe tags.
- AC-004/005: frozen nested models, JSON round-trips, staged/unstaged config edits,
  branch advance, unchanged snapshot/source digest, and deterministic serialization.
- AC-006/007: chained errors, public imports, regression suite, documentation review.

Avoid input cross-products and repeated SHA-constraint matrices. Reuse current
Git test fixtures for integration cases. Finish with uv run pytest,
uv run ruff check ., and uv run pyright. A writable UV_CACHE_DIR override is allowed.
