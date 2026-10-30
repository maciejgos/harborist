"""System-Git validation and locked branch advancement for explicit application."""

import os
import select
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import TypeAdapter

from shipyard.domain import GitCommitSha
from shipyard.git.command import git_environment
from shipyard.git.errors import GitWorkspaceError

if TYPE_CHECKING:
    from shipyard.git.repository import GitRepository


_COMMIT_SHA_ADAPTER = TypeAdapter(GitCommitSha)


class GitApplication:
    """Application operations composed behind the GitRepository facade."""

    def __init__(
        self, *, repository: GitRepository, path: Path, run: Callable[..., bytes]
    ) -> None:
        self._repository = repository
        self._path = path
        self._run = run

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
        root = self._repository.checkout_root()
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
            self._repository.require_normal_index_tracking()
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
                    env=git_environment(),
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
                self._repository.require_clean_revision(commit_sha=candidate)
            if self.branch_sha(branch) != candidate:
                raise GitWorkspaceError(
                    "Resulting target does not match verified candidate"
                )
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise GitWorkspaceError(
                f"Cannot advance target; partial state is retained: {error}; inspect checkout before retrying"
            ) from error
