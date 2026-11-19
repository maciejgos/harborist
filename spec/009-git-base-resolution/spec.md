# Specification: Git base SHA resolution

## Acceptance criteria

- **AC-001 — API:** Export GitRepository and GitResolutionError through
  harborist.git. GitRepository(path=Path) stores the supplied path without I/O.
  resolve_base(*, ref: str = "HEAD") returns a GitCommitSha. Each call resolves
  afresh; no symbolic-ref caching or implicit refresh of returned values occurs.
- **AC-002 — Native resolution:** Invoke system Git through subprocess.run with
  an argument list and no shell, using git -C <repository> rev-parse --verify
  --end-of-options <ref>^{commit}. Preserve Git's native commit-ish interpretation
  and name precedence. Support branches, annotated commit tags, ancestor expressions,
  full/unambiguous abbreviated hashes, detached HEAD, subdirectories, and bare repos.
- **AC-003 — Exact identity:** Require process success, decode stdout as ASCII,
  strip surrounding output whitespace, and validate one full lowercase SHA-1 or
  SHA-256 hash through GitCommitSha. Reject missing refs, unborn HEAD, revision
  sets, non-commit targets, and malformed successful output. Empty ref is rejected
  without substituting HEAD. Option-like inputs remain positional data.
- **AC-004 — Environment:** Copy the parent environment, removing GIT_DIR,
  GIT_WORK_TREE, GIT_COMMON_DIR, GIT_IMPLICIT_WORK_TREE, GIT_OBJECT_DIRECTORY,
  GIT_ALTERNATE_OBJECT_DIRECTORIES, GIT_INDEX_FILE, GIT_NAMESPACE, GIT_PREFIX,
  GIT_SHALLOW_FILE, GIT_GRAFT_FILE, and GIT_REPLACE_REF_BASE. Preserve remaining
  environment/normal configuration and set GIT_OPTIONAL_LOCKS=0 in the copy.
  Do not mutate the parent environment.
- **AC-005 — Failure boundary:** GitResolutionError derives from ValueError and
  includes repository/ref context. Preserve launch, process, output-decoding, and
  output-validation exceptions as causes. Empty input needs no fabricated cause.
- **AC-006 — Read-only behavior:** Introduce no checkout, fetch, reset, commit,
  or ref-update commands. Preserve branches, index, tracked modifications, and
  untracked files. Advancing a branch cannot change a previously returned hash;
  subsequent explicit resolution may return the new commit.
- **AC-007 — Scope and documentation:** Reuse existing domain hash validation;
  add no dependencies or generic subprocess framework. Document the adapter API
  and implemented capability in README/ARCHITECTURE.md, keeping specifications
  separate from implementation.

## Completion and exclusions

Callers can obtain an exact existing commit identity without changing developer
state. This does not yet freeze a Run base or complete Phase 2. Defer worktrees,
candidate commits/refs, GitHub/CLI integration, frozen configuration, and the Run
contract. No repository state is retained except its supplied path.

Implementation may revise plan.md; acceptance changes must be explicit.
