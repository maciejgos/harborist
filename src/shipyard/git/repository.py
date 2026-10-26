"""Resolve exact commit identities through the system Git executable."""

import os
import subprocess
from pathlib import Path, PurePosixPath

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

    def create_workspace(self, *, attempt: Attempt, path: Path) -> GitWorkspace:
        """Create a fresh detached checkout without touching developer files."""
        path = path.absolute()
        try:
            root = Path(self._run("rev-parse", "--show-toplevel").decode().strip())
            if path.resolve().is_relative_to(root.resolve()) or path.exists():
                raise ValueError("Workspace must be fresh and outside source checkout")
            if (
                self._run("--no-replace-objects", "cat-file", "-t", attempt.start_sha)
                != b"commit\n"
            ):
                raise ValueError("Workspace base must be an actual commit")
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
            raise GitWorkspaceError("Cannot create isolated workspace") from error
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

    def publish_candidate(self) -> Candidate:
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
            if _run_git(
                self.path, "ls-files", "--others", "--ignored", "--exclude-standard"
            ):
                raise ValueError("Remove ignored BUILD residue before publication")
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
                f"Shipyard candidate for {self.attempt.attempt_id}",
            )
            sha = repository.resolve_base()
            repository.require_clean_revision(commit_sha=sha)
            _run_git(self.path, "update-ref", self.candidate_ref, sha, "0" * len(sha))
            return self.attempt.create_candidate(sha)
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                "Cannot publish candidate; workspace retained"
            ) from error


def _run_git(path: Path, *args: str) -> bytes:
    environment = os.environ.copy()
    for name in _REPOSITORY_OVERRIDES:
        environment.pop(name, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        env=environment,
    ).stdout
