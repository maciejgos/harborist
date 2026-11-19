from pathlib import Path
from uuid import uuid4

import pytest

from harborist.git.repository import GitRepository
from tests.git_helpers import git, init_repository


@pytest.fixture
def target(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    init_repository(repo)
    (repo / "file").write_text("base")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "file").write_text("candidate")
    git(repo, "commit", "-am", "candidate")
    candidate = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "--detach", base)
    git(repo, "branch", "-f", "main", base)
    git(repo, "checkout", "main")
    return repo, base, candidate


def test_checked_out_fast_forward(target: tuple[Path, str, str]) -> None:
    repo, base, candidate = target
    repository = GitRepository(path=repo)
    repository.advance_branch(branch="main", previous=base, candidate=candidate)
    assert git(repo, "rev-parse", "HEAD") == candidate
    assert (repo / "file").read_text() == "candidate"
    assert git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    "kind", ["unstaged", "staged", "untracked", "ignored", "operation"]
)
def test_dirty_refusal(target: tuple[Path, str, str], kind: str) -> None:
    repo, base, candidate = target
    if kind in ("unstaged", "staged"):
        (repo / "file").write_text("user")
        if kind == "staged":
            git(repo, "add", ".")
    elif kind == "operation":
        (repo / ".git" / "CHERRY_PICK_HEAD").write_text(candidate)
    else:
        (repo / "user").write_text("precious")
        if kind == "ignored":
            (repo / ".git" / "info" / "exclude").write_text("user\n")
    with pytest.raises(ValueError, match="clean|operation"):
        GitRepository(path=repo).advance_branch(
            branch="main", previous=base, candidate=candidate
        )
    assert git(repo, "rev-parse", "main") == base


def test_unoccupied_and_race(target: tuple[Path, str, str]) -> None:
    repo, base, candidate = target
    git(repo, "branch", "other", base)
    (repo / "file").write_text("user")
    repository = GitRepository(path=repo)
    repository.advance_branch(branch="other", previous=base, candidate=candidate)
    assert git(repo, "rev-parse", "other") == candidate
    assert (repo / "file").read_text() == "user"
    with pytest.raises(ValueError, match="changed|advance"):
        repository.advance_branch(branch="other", previous=base, candidate=candidate)


def test_other_worktree(target: tuple[Path, str, str], tmp_path: Path) -> None:
    repo, base, candidate = target
    other = tmp_path / "other"
    git(repo, "branch", "occupied", base)
    git(repo, "worktree", "add", str(other), "occupied")
    with pytest.raises(ValueError, match="worktree.*other"):
        GitRepository(path=repo).advance_branch(
            branch="occupied", previous=base, candidate=candidate
        )
    assert git(repo, "rev-parse", "occupied") == base


def test_candidate_identity(target: tuple[Path, str, str]) -> None:
    repo, base, candidate = target
    run_id = uuid4()
    repository = GitRepository(path=repo)
    with pytest.raises(ValueError, match="candidate"):
        repository.validate_application_candidate(
            run_id=run_id, base=base, candidate=candidate
        )
    git(repo, "update-ref", f"refs/shipyard/runs/{run_id}/candidate", candidate)
    repository.validate_application_candidate(
        run_id=run_id, base=base, candidate=candidate
    )


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_hidden_tracked_edits_are_protected(
    target: tuple[Path, str, str], flag: str
) -> None:
    repo, base, candidate = target
    git(repo, "update-index", flag, "file")
    (repo / "file").write_text("precious hidden edit")
    with pytest.raises(ValueError):
        GitRepository(path=repo).advance_branch(
            branch="main", previous=base, candidate=candidate
        )
    assert (repo / "file").read_text() == "precious hidden edit"
    assert git(repo, "rev-parse", "main") == base


def test_missing_and_mismatched_candidate_ref(target: tuple[Path, str, str]) -> None:
    repo, base, candidate = target
    run_id = uuid4()
    git(repo, "update-ref", f"refs/shipyard/runs/{run_id}/candidate", base)
    with pytest.raises(ValueError, match="candidate"):
        GitRepository(path=repo).validate_application_candidate(
            run_id=run_id, base=base, candidate=candidate
        )
    git(repo, "update-ref", f"refs/shipyard/runs/{run_id}/candidate", candidate)
    git(repo, "replace", base, candidate)
    with pytest.raises(ValueError, match="Replacement"):
        GitRepository(path=repo).validate_application_candidate(
            run_id=run_id, base=base, candidate=candidate
        )


@pytest.mark.parametrize(
    "branch", ["-main", "../main", "missing", "refs/remotes/origin/main"]
)
def test_local_branch_required(target: tuple[Path, str, str], branch: str) -> None:
    repo, base, candidate = target
    with pytest.raises(ValueError, match="local branch"):
        GitRepository(path=repo).preflight_application(
            branch=branch, candidate=candidate
        )
    assert git(repo, "rev-parse", "main") == base


def test_hooks_disabled(target: tuple[Path, str, str]) -> None:
    repo, base, candidate = target
    hook = repo / ".git" / "hooks" / "reference-transaction"
    hook.write_text('#!/bin/sh\ntouch "' + str(repo / "hook-ran") + '"\nexit 1\n')
    hook.chmod(0o755)
    GitRepository(path=repo).advance_branch(
        branch="main", previous=base, candidate=candidate
    )
    assert not (repo / "hook-ran").exists()
    assert git(repo, "rev-parse", "main") == candidate


def test_checkout_update_holds_target_lock(
    target: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    repo, base, candidate = target
    original = GitRepository._run  # pyright: ignore[reportPrivateUsage]
    locked: list[bool] = []

    def inspect(self: GitRepository, *args: str) -> bytes:
        if "read-tree" in args:
            with pytest.raises(subprocess.CalledProcessError):
                git(repo, "update-ref", "refs/heads/main", candidate, base)
            locked.append(True)
        return original(self, *args)

    monkeypatch.setattr(GitRepository, "_run", inspect)
    GitRepository(path=repo).advance_branch(
        branch="main", previous=base, candidate=candidate
    )
    assert locked == [True]
    assert git(repo, "rev-parse", "main") == candidate


def test_intervening_unoccupied_ref_change_is_refused(
    target: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base, candidate = target
    git(repo, "branch", "other", base)
    original = GitRepository._run  # pyright: ignore[reportPrivateUsage]

    def race(self: GitRepository, *args: str) -> bytes:
        if "update-ref" in args:
            git(repo, "update-ref", "refs/heads/other", candidate, base)
        return original(self, *args)

    monkeypatch.setattr(GitRepository, "_run", race)
    with pytest.raises(ValueError, match="partial state"):
        GitRepository(path=repo).advance_branch(
            branch="other", previous=base, candidate=candidate
        )
    assert git(repo, "rev-parse", "other") == candidate
    assert git(repo, "rev-parse", "HEAD") == base
    assert (repo / "file").read_text() == "base"
