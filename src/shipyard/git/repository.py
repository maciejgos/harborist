"""Resolve exact commit identities through the system Git executable."""

import os
import subprocess
from pathlib import Path

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


class GitRepository:
    """A supplied repository path; symbolic refs are resolved on each call."""

    def __init__(self, *, path: Path) -> None:
        self._path = path

    def resolve_base(self, *, ref: str = "HEAD") -> GitCommitSha:
        context = f"Cannot resolve Git ref {ref!r} in repository {self._path}"
        if not ref:
            raise GitResolutionError(context)
        environment = os.environ.copy()
        for name in _REPOSITORY_OVERRIDES:
            environment.pop(name, None)
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self._path),
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"{ref}^{{commit}}",
                ],
                check=True,
                capture_output=True,
                env=environment,
            )
            return _COMMIT_SHA_ADAPTER.validate_python(
                result.stdout.decode("ascii").strip()
            )
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            raise GitResolutionError(context) from error
