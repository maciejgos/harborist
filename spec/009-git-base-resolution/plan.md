# Plan: Git base SHA resolution

## Implementation sequence

1. Record intake/specification before code.
2. Write temporary-repository tests for default/explicit resolution and confirm
   failure, then implement GitRepository and its public exports.
3. Test failure handling, environment redirection, native ref forms, and read-only
   behavior. Confirm missing behavior fails before implementing it. Refactor with
   checks green.
4. Update README/architecture; run the full required validation set.

## Adapter

Add shipyard.git.GitRepository(path=Path) and GitResolutionError(ValueError).
The constructor performs no I/O. resolve_base(*, ref="HEAD") rejects an empty
string, copies/sanitizes the environment as specified, and executes the exact
argument-list command from spec.md with check=True, capture_output=True, no shell,
and GIT_OPTIONAL_LOCKS=0. Keep provider/tool behavior out of the domain.

Decode stdout as ASCII, strip surrounding whitespace, and validate GitCommitSha
using TypeAdapter. Wrap launch/process/decode/validation errors with repository/ref
context and exception chaining. Use no generic runner or extra identity model.

Ref inputs retain Git's interpretation, including tag peeling via ^{commit}.
Validation is commit-specific; a hash-shaped string alone is insufficient.
Resolve on every explicit call; the future Run use case must call once and persist
the result rather than repeatedly resolving a moving branch.

## Test mapping

- AC-001/002: constructor without I/O; real HEAD/branch, full/short hashes, ancestor,
  annotated tag, detached HEAD, subdirectory, and local bare repository resolution.
- AC-003/005: empty/missing refs, unborn HEAD, tree targets, revision sets, leading
  option-like input, and targeted missing-Git/malformed-output fakes with causes.
- AC-004: inherited repository redirects ignored, subprocess copy sanitized, normal
  configuration retained, and parent environment unchanged.
- AC-006: saved SHA remains fixed after a new commit; a new call returns new HEAD;
  dirty index/worktree/untracked bytes and branch state remain unchanged.
- AC-003/007: dedicated SHA-256 repository, regression suite, and documentation review.

Use local test-only Git configuration/identity in temporary repositories. Avoid
cross-products of object format/ref syntax and broad fake frameworks. Finish with
uv run pytest, uv run ruff check ., and uv run pyright; a writable UV_CACHE_DIR
override may be used without changing project configuration.
