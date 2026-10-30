"""Resolve exact commit identities through the system Git executable."""

import os
import select
import stat
import subprocess
from pathlib import Path, PurePosixPath
from uuid import UUID

from pydantic import TypeAdapter

from shipyard.domain import Attempt, Candidate, GitCommitSha

_COMMIT_SHA_ADAPTER = TypeAdapter(GitCommitSha)
_REPOSITORY_OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_GRAFT_FILE",
    "GIT_REPLACE_REF_BASE",
)


class GitResolutionError(ValueError):
    """A commit-ish could not be resolved to a validated full commit identity."""


class GitReadError(ValueError):
    """A committed blob could not be read at an exact commit identity."""


class GitRepository:
    """A supplied repository path; symbolic refs are resolved on each call."""

    def __init__(self, *, path: Path) -> None:
        self._path = path

    def resolve_base(self, *, ref: str = "HEAD") -> GitCommitSha:
        context = f"Cannot resolve Git ref {ref!r} in repository {self._path}"
        if not ref:
            raise GitResolutionError(context)
        try:
            output = self._run(
                "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"
            )
            return _COMMIT_SHA_ADAPTER.validate_python(output.decode("ascii").strip())
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitResolutionError(context) from error

    def checkout_root(self) -> Path:
        """Resolve the actual source checkout through Git, including path aliases."""
        try:
            return Path(
                self._run("rev-parse", "--show-toplevel").decode().removesuffix("\n")
            ).resolve()
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Cannot resolve Git repository {self._path}; supply --repo with an available checkout"
            ) from error

    def preflight_workspace(self, *, base_sha: GitCommitSha, path: Path) -> Path:
        """Read-only validation before lifecycle admission; creation rechecks races."""
        root = self.checkout_root()
        try:
            base_sha = _COMMIT_SHA_ADAPTER.validate_python(base_sha)
            if (
                self._run("--no-replace-objects", "cat-file", "-t", base_sha)
                != b"commit\n"
            ):
                raise ValueError("Expected an actual commit")
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Frozen base commit {base_sha} is unavailable in repository {root}; "
                "restore the frozen commit or supply the original --repo checkout"
            ) from error
        try:
            # Inspect lexical ancestors before resolve: a dangling intermediate
            # symlink must not be mistaken for an ordinary missing directory.
            for component in (path, *path.parents):
                if component.is_symlink():
                    component.resolve(strict=True)
            normalized = path.resolve()
            if (
                path.exists()
                or path.is_symlink()
                or normalized.is_relative_to(root)
                or root.is_relative_to(normalized)
            ):
                raise ValueError("Existing destination or overlap with source checkout")
            parent = normalized.parent
            while True:
                try:
                    metadata = parent.stat()
                except FileNotFoundError:
                    parent = parent.parent
                    continue
                if not stat.S_ISDIR(metadata.st_mode):
                    raise ValueError(
                        f"Required directory {parent} is obstructed by a file"
                    )
                if not os.access(parent, os.W_OK | os.X_OK):
                    raise PermissionError(
                        f"Access denied to required directory {parent}"
                    )
                break
        except (OSError, ValueError, RuntimeError) as error:
            raise GitWorkspaceError(
                f"Invalid workspace {path}: {error}; supply --workspace with a fresh path "
                f"outside source checkout {root}"
            ) from error
        return normalized

    def create_workspace(self, *, attempt: Attempt, path: Path) -> GitWorkspace:
        """Create a fresh detached checkout without touching developer files."""
        path = self.preflight_workspace(base_sha=attempt.start_sha, path=path)
        try:
            self._run(
                "--no-replace-objects",
                "-c",
                f"core.hooksPath={os.devnull}",
                "worktree",
                "add",
                "--detach",
                str(path),
                attempt.start_sha,
            )
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Cannot create isolated workspace {path}: {error}"
            ) from error
        return GitWorkspace(path=path, attempt=attempt)

    def read_file_at_commit(self, *, commit_sha: GitCommitSha, path: str) -> bytes:
        """Read a repository-root-relative blob without consulting mutable refs/files."""
        commit_sha = _COMMIT_SHA_ADAPTER.validate_python(commit_sha)
        context = (
            f"Cannot read Git file {path!r} at {commit_sha} in repository {self._path}"
        )
        try:
            relative = PurePosixPath(path)
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Expected a nonempty repository-root-relative path")
            if (
                self._run("--no-replace-objects", "cat-file", "-t", commit_sha)
                != b"commit\n"
            ):
                raise ValueError("Expected a commit identity without tag peeling")
            return self._run(
                "--no-replace-objects",
                "cat-file",
                "blob",
                f"{commit_sha}:{relative.as_posix()}",
            )
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitReadError(context) from error

    def require_clean_revision(self, *, commit_sha: GitCommitSha) -> None:
        """Assert an existing checkout is clean at an exact candidate; never checkout."""
        if self.resolve_base() != commit_sha:
            raise GitReadError("Workspace HEAD must match exact candidate SHA")
        try:
            if self._run("status", "--porcelain", "--untracked-files=all", "--ignored"):
                raise GitReadError("REVIEW requires a clean candidate workspace")
        except (OSError, subprocess.CalledProcessError) as error:
            raise GitReadError("Cannot inspect candidate workspace") from error

    def validate_application_candidate(
        self, *, run_id: UUID, base: str, candidate: str
    ) -> None:
        """Require original commit objects and the durable Run-owned ref."""
        try:
            for sha in (base, candidate):
                _COMMIT_SHA_ADAPTER.validate_python(sha)
                if self._run("cat-file", "-t", sha) != b"commit\n":
                    raise ValueError("Expected an actual commit object")
                if self._run("for-each-ref", f"refs/replace/{sha}"):
                    raise ValueError("Replacement objects cannot authorize application")
            if (
                self._run(
                    "rev-parse", "--verify", f"refs/shipyard/runs/{run_id}/candidate"
                )
                .decode()
                .strip()
                != candidate
            ):
                raise ValueError("Run-owned candidate ref does not match")
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Invalid or unavailable base/candidate: {error}; restore the original "
                "repository and Run-owned candidate ref before retrying"
            ) from error

    def branch_sha(self, branch: str) -> str:
        """Accept only a valid, existing, nonsymbolic local branch."""
        try:
            if not branch or branch.startswith("-"):
                raise ValueError("Invalid branch name")
            ref = f"refs/heads/{branch}"
            self._run("check-ref-format", "--branch", branch)
            self._run("check-ref-format", ref)
            if self._run("for-each-ref", "--format=%(symref)", ref).strip():
                raise ValueError("Symbolic target branch is unsupported")
            sha = self._run("show-ref", "--verify", "--hash", ref).decode().strip()
            _COMMIT_SHA_ADAPTER.validate_python(sha)
            if self._run("cat-file", "-t", sha) != b"commit\n":
                raise ValueError("Branch must identify an actual commit")
            return sha
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Invalid or missing local branch {branch!r}; supply --branch with an "
                "existing local branch (remote-only references are unsupported)"
            ) from error

    def _application_checkout(self, branch: str) -> bool:
        root = self.checkout_root()
        selected = False
        # Porcelain -z represents even whitespace/newline-containing paths exactly.
        for record in self._run("worktree", "list", "--porcelain", "-z").split(b"\0\0"):
            fields = record.split(b"\0")
            if f"branch refs/heads/{branch}".encode() not in fields:
                continue
            paths = [os.fsdecode(f[9:]) for f in fields if f.startswith(b"worktree ")]
            if len(paths) != 1:
                raise GitWorkspaceError("Ambiguous target worktree occupancy")
            path = Path(paths[0])
            if (
                path.resolve() != root
                or any(f.startswith((b"locked", b"prunable")) for f in fields)
                or not path.is_dir()
            ):
                raise GitWorkspaceError(
                    f"Target is occupied by worktree {path}; free the branch before retrying"
                )
            selected = True
        return selected

    def preflight_application(self, *, branch: str, candidate: str) -> str:
        previous = self.branch_sha(branch)
        if previous == candidate:
            return previous
        try:
            self._run("merge-base", "--is-ancestor", previous, candidate)
        except subprocess.CalledProcessError as error:
            raise GitWorkspaceError(
                "Target is ahead of or diverged from the candidate; create a new Run "
                "against the updated target"
            ) from error
        if self._application_checkout(branch):
            if self._run("status", "--porcelain", "--untracked-files=all", "--ignored"):
                raise GitWorkspaceError(
                    "Application requires a clean index and checkout, including untracked "
                    "and ignored files; preserve your changes elsewhere before retrying"
                )
            flags = self._run("ls-files", "-v", "-z").split(b"\0")
            if any(f and (f[:1].islower() or f.startswith(b"S ")) for f in flags):
                raise GitWorkspaceError(
                    "Application requires tracked files without assume-unchanged or "
                    "skip-worktree flags; preserve local edits and restore normal index tracking before retrying"
                )
            for marker in (
                "MERGE_HEAD",
                "CHERRY_PICK_HEAD",
                "REVERT_HEAD",
                "rebase-merge",
                "rebase-apply",
                "sequencer",
                "BISECT_LOG",
                "BISECT_START",
            ):
                path = Path(
                    os.fsdecode(self._run("rev-parse", "--git-path", marker)).strip()
                )
                if not path.is_absolute():
                    path = self._path / path
                if path.exists() or path.is_symlink():
                    raise GitWorkspaceError(
                        f"Git operation in progress ({marker}); finish or abort it yourself before retrying"
                    )
            if self._run("ls-files", "--unmerged"):
                raise GitWorkspaceError(
                    "Resolve unmerged index entries before retrying"
                )
        return previous

    def advance_branch(self, *, branch: str, previous: str, candidate: str) -> None:
        """Fast-forward with expected-old locking, without hooks or rollback.

        The ref transaction is prepared before checkout writes and held through
        read-tree. Failed writes retain partial checkout state for inspection.
        """
        if self.branch_sha(branch) != previous:
            raise GitWorkspaceError(
                "Target changed before advancement; retry with a new Run if needed"
            )
        observed = self.preflight_application(branch=branch, candidate=candidate)
        if observed != previous:
            raise GitWorkspaceError("Target changed before advancement")
        if previous == candidate:
            return
        ref = f"refs/heads/{branch}"
        try:
            if not self._application_checkout(branch):
                self._run(
                    "-c",
                    f"core.hooksPath={os.devnull}",
                    "update-ref",
                    "--no-deref",
                    ref,
                    candidate,
                    previous,
                )
            else:
                process = subprocess.Popen(
                    [
                        "git",
                        "-C",
                        str(self._path),
                        "-c",
                        f"core.hooksPath={os.devnull}",
                        "update-ref",
                        "--no-deref",
                        "--stdin",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=_git_environment(),
                )
                assert process.stdin is not None and process.stdout is not None
                try:
                    process.stdin.write(
                        f"start\nupdate {ref} {candidate} {previous}\nprepare\n".encode()
                    )
                    process.stdin.flush()
                    reply = b""
                    while b"prepare: ok\n" not in reply:
                        if not select.select([process.stdout], [], [], 10)[0]:
                            raise GitWorkspaceError(
                                "Timed out preparing expected-old Git transaction"
                            )
                        chunk = os.read(process.stdout.fileno(), 4096)
                        if not chunk:
                            raise GitWorkspaceError(
                                "Git refused expected-old transaction; target may have changed"
                            )
                        reply += chunk
                    self._run(
                        "-c",
                        f"core.hooksPath={os.devnull}",
                        "read-tree",
                        "-u",
                        "-m",
                        previous,
                        candidate,
                    )
                    _, stderr = process.communicate(b"commit\n", timeout=10)
                    if process.returncode:
                        raise GitWorkspaceError(
                            f"Git ref commit failed: {stderr.decode(errors='replace')}"
                        )
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=10)
                self.require_clean_revision(commit_sha=candidate)
            if self.branch_sha(branch) != candidate:
                raise GitWorkspaceError(
                    "Resulting target does not match verified candidate"
                )
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Cannot advance target; partial state is retained: {error}; inspect checkout before retrying"
            ) from error

    def _run(self, *args: str) -> bytes:
        return _run_git(self._path, *args)


class GitWorkspaceError(ValueError):
    """A workspace or candidate operation failed; partial state is retained."""


class GitWorkspace:
    """An explicit isolated checkout bound to one immutable Attempt."""

    def __init__(self, *, path: Path, attempt: Attempt) -> None:
        self.path = path
        self.attempt = attempt

    @property
    def candidate_ref(self) -> str:
        """Stable Run-owned reachability; publication never replaces it."""
        return f"refs/shipyard/runs/{self.attempt.run_id}/candidate"

    def clean_ignored_files(self) -> None:
        """Remove disposable ignored files only from this owned linked worktree.

        Never force removal of nested repositories or follow directory symlinks.
        Tracked changes and nonignored untracked files are retained for validation.
        """
        if not (self.path / ".git").is_file() or (
            _run_git(self.path, "rev-parse", "--abbrev-ref", "HEAD").strip() != b"HEAD"
        ):
            raise GitReadError("Cleanup requires an isolated detached worktree")
        try:
            _run_git(self.path, "clean", "-f", "-d", "-X", "--", ".")
        except (OSError, subprocess.CalledProcessError) as error:
            raise GitReadError(
                "Cannot clean ignored files in isolated workspace"
            ) from error

    def publish_candidate(self, *, message: str) -> Candidate:
        """Commit BUILD changes and publish a create-only candidate ref.

        Caller must stop BUILD before calling; concurrent workspace writers are
        unsupported. Partial commits are retained when ref publication fails.
        """
        repository = GitRepository(path=self.path)
        try:
            if repository.resolve_base() != self.attempt.start_sha:
                raise ValueError("BUILD must leave HEAD at the frozen start SHA")
            if (
                _run_git(self.path, "rev-parse", "--abbrev-ref", "HEAD").strip()
                != b"HEAD"
            ):
                raise ValueError("Candidate requires detached HEAD")
            if _run_git(self.path, "ls-files", "--unmerged"):
                raise ValueError("Candidate cannot contain unresolved merges")
            self.clean_ignored_files()
            _run_git(self.path, "add", "--all", "--", ".")
            _run_git(
                self.path,
                "-c",
                "user.name=Shipyard",
                "-c",
                "user.email=shipyard@localhost",
                "-c",
                "commit.gpgsign=false",
                "-c",
                f"core.hooksPath={os.devnull}",
                "commit",
                "--allow-empty",
                "--no-verify",
                "-m",
                message,
            )
            sha = repository.resolve_base()
            repository.require_clean_revision(commit_sha=sha)
            _run_git(self.path, "update-ref", self.candidate_ref, sha, "0" * len(sha))
            return self.attempt.create_candidate(sha)
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Cannot publish candidate; workspace retained: {error}"
            ) from error


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in _REPOSITORY_OVERRIDES:
        environment.pop(name, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def _run_git(path: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        env=_git_environment(),
    ).stdout
