# Plan: Filesystem intent persistence

## Implementation

1. Prepare intake/specification before implementation.
2. Write save/load integration tests with temporary directories; confirm failure,
   then implement the concrete FileIntentStore and private metadata model.
3. Test repeat saves, partial state, and exclusive file creation before implementing
   conflict handling. Add integrity/failure cases and confirm missing behavior
   fails before fixing it. Refactor with checks green.
4. Update README/architecture and run full validation.

FileIntentStore(root=Path) stores the supplied root without I/O. save accepts an
IntentSnapshot; revalidate from its dumped data before any writes. Serialize
source_ref/artifact using a private frozen Pydantic metadata model with forbidden
extras. Reuse existing domain constraints; no new public domain model is required.

Create the Run directory as needed, preflight both reserved paths (including
existing symlink entries), then write binary files with exclusive creation. Write
and close intent.md before creating intent.json. Exclusive creation also handles
an intervening conflict after preflight. Retain partial files on failure.

load validates the requested UUID, reads intent.json metadata, reads/decode-UTF-8
intent.md, constructs IntentSnapshot, and compares its owner ID to the requested
Run. Do not regenerate identities or consult the original source. Reject unknown
metadata fields including a duplicated markdown field.

Catch I/O and persisted-data validation errors at the persistence boundary,
preserving causes. Conflict detection raises IntentAlreadyExistsError; actual
exclusive-open conflicts preserve their FileExistsError cause. Detected preexisting
paths need no fabricated underlying exception. Caller validation is outside the
I/O error wrapper. Error messages identify operation/path without formatting
validation details that could expose captured content.

## Test mapping

- AC-001/002: no constructor I/O, exact byte round-trips (including empty content),
  metadata-only JSON, preserved identities, and unchanged unrelated Run files.
- AC-003/004: matching/different repeat saves, either orphan file, exclusive-open
  conflict, and simulated metadata-write failure with no automatic cleanup/repair.
- AC-005: source edit/deletion independence; missing files, malformed/extra metadata,
  invalid UTF-8, modified bytes, invalid artifact scope, and wrong Run ownership.
- AC-006: representative chained I/O/validation failures, no content in outer
  messages, and rejected invalid caller data before filesystem mutation.
- AC-007: existing regression suite and documentation/source review.

Use focused temporary-directory integration tests and targeted failure injection;
reuse existing domain constraint tests instead of input matrices. Finish with
uv run pytest, uv run ruff check ., and uv run pyright. A writable UV_CACHE_DIR
override is permitted for the sandbox without changing project configuration.
