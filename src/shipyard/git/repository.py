"""Resolve exact commit identities through the system Git executable."""

import os
import stat
import subprocess
from pathlib import Path, PurePosixPath
from uuid import UUID

from pydantic import TypeAdapter

from shipyard.domain import Attempt, Candidate, GitCommitSha
from shipyard.git.application import GitApplication
from shipyard.git.command import run_git as _run_git
from shipyard.git.errors import GitReadError, GitResolutionError, GitWorkspaceError

__all__ = [
    "GitReadError",
    "GitRepository",
    "GitResolutionError",
    "GitWorkspace",
    "GitWorkspaceError",
]

_COMMIT_SHA_ADAPTER = TypeAdapter(GitCommitSha)


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

    def require_normal_index_tracking(self) -> None:
        """Reject index flags that can hide differences from the exact commit."""
        try:
            flags = self._run("ls-files", "-v", "-z").split(b"\0")
            if any(f and (f[:1].islower() or f.startswith(b"S ")) for f in flags):
                raise GitReadError(
                    "Tracked files require normal index tracking without assume-unchanged "
                    "or skip-worktree flags; preserve local edits and restore normal index tracking"
                )
        except (OSError, subprocess.CalledProcessError) as error:
            raise GitReadError("Cannot inspect candidate index tracking") from error

    def require_clean_revision(self, *, commit_sha: GitCommitSha) -> None:
        """Assert an existing checkout is clean at an exact candidate; never checkout."""
        if self.resolve_base() != commit_sha:
            raise GitReadError("Workspace HEAD must match exact candidate SHA")
        self.require_normal_index_tracking()
        try:
            if self._run("status", "--porcelain", "--untracked-files=all", "--ignored"):
                raise GitReadError("REVIEW requires a clean candidate workspace")
        except (OSError, subprocess.CalledProcessError) as error:
            raise GitReadError("Cannot inspect candidate workspace") from error

    def validate_application_candidate(
        self, *, run_id: UUID, base: str, candidate: str, attempt_id: UUID | None = None
    ) -> None:
        """Require original commit objects and the durable Run-owned ref."""
        self._application().validate_application_candidate(
            run_id=run_id, base=base, candidate=candidate, attempt_id=attempt_id
        )

    def branch_sha(self, branch: str) -> str:
        """Resolve an existing, nonsymbolic local branch."""
        return self._application().branch_sha(branch)

    def preflight_application(self, *, branch: str, candidate: str) -> str:
        """Validate target ancestry, occupancy and checkout state."""
        return self._application().preflight_application(
            branch=branch, candidate=candidate
        )

    def advance_branch(self, *, branch: str, previous: str, candidate: str) -> None:
        """Advance an eligible branch with expected-old locking."""
        self._application().advance_branch(
            branch=branch, previous=previous, candidate=candidate
        )

    def _application(self) -> GitApplication:
        return GitApplication(repository=self, path=self._path, run=self._run)

    def _run(self, *args: str) -> bytes:
        return _run_git(self._path, *args)


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

    def publish_candidate(
        self, *, message: str, attempt_scoped: bool = False
    ) -> Candidate:
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
            repository.require_normal_index_tracking()
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
            ref = (
                f"refs/shipyard/runs/{self.attempt.run_id}/attempts/{self.attempt.attempt_id}/candidate"
                if attempt_scoped
                else self.candidate_ref
            )
            _run_git(self.path, "update-ref", ref, sha, "0" * len(sha))
            return self.attempt.create_candidate(sha)
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Cannot publish candidate; workspace retained: {error}"
            ) from error
