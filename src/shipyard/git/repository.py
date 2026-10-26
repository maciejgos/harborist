"""Resolve exact commit identities through the system Git executable."""

import os
import subprocess
from pathlib import Path, PurePosixPath

from pydantic import TypeAdapter

from shipyard.domain import GitCommitSha

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

    def _run(self, *args: str) -> bytes:
        environment = os.environ.copy()
        for name in _REPOSITORY_OVERRIDES:
            environment.pop(name, None)
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        return subprocess.run(
            ["git", "-C", str(self._path), *args],
            check=True,
            capture_output=True,
            env=environment,
        ).stdout
