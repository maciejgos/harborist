# Plan: Markdown intake and immutable source snapshot

## Implementation sequence

1. Record intent and acceptance before code.
2. Write focused snapshot tests and confirm failure, then add IntentSnapshot
   with frozen Pydantic validation, derived run_id, and artifact consistency checks.
3. Write temporary-directory file intake tests and confirm failure, then add the
   concrete adapter and its error type. Keep I/O out of the domain.
4. Add representative failure/boundary tests before implementing any missing
   behavior, then refactor with checks green.
5. Update README and the architecture code map. Run full validation.

## Interfaces and data flow

IntentSnapshot has source_ref, markdown, and artifact fields. Its keyword-only
create(run_id, source_ref, markdown) factory measures UTF-8 bytes using
ArtifactReference.create with INTENT/INTAKE and no Attempt. An after validator
checks that supplied metadata matches content and scope, including deserialization.
run_id is an ordinary property and is not serialized. Strings are strict; the
source reference must be nonempty. No rigid issue schema is introduced.

read_markdown_intent(*, run_id: UUID, path: Path) resolves the path, calls
read_bytes once, decodes utf-8, and passes file:<resolved absolute path> plus
content to the domain factory. Preserve BOM via utf-8 rather than utf-8-sig;
byte reading avoids newline conversion. No writes, extension filtering, Run
transitions, file: argument parsing, or storage abstraction is needed.

Catch OSError and UnicodeDecodeError around filesystem/decoding work only;
raise MarkdownIntakeError(ValueError) with exception chaining. Let domain
validation errors propagate without reclassification.

## Test mapping

- AC-001/002: creation, ownership, exact digest/size, JSON round-trip, representative
  frozen/extra/type constraints, and invalid artifact scope/content relationships.
- AC-003: real files with Unicode/front matter, BOM/CRLF, and empty content.
- AC-004/005: relative/resolved provenance, non-md extension, symlink resolution,
  one read, unchanged source/no added files, and independent snapshots after edits
  and deletion.
- AC-006: missing file, directory, invalid UTF-8, simulated PermissionError, and
  exception chaining; invalid Run ID remains a domain validation error.
- AC-007/008: public imports, regression suite, and source/documentation review.

Use temporary directories for I/O and one targeted permission fake for portable
failure simulation. Reuse existing hash-constraint coverage; avoid Cartesian
products or repeating validation through every API path.

Finish with uv run pytest, uv run ruff check ., and uv run pyright. A writable
UV_CACHE_DIR override may be used for the sandbox without changing configuration.
