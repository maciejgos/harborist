"""Real Git workspace and candidate acceptance boundaries."""

from pathlib import Path
from uuid import uuid4

import pytest

from shipyard.domain import Attempt
from shipyard.git import GitRepository
from tests.git_helpers import git, init_repository


def source(tmp_path: Path) -> tuple[Path, Attempt]:
    repo = tmp_path / "source"
    init_repository(repo)
    (repo / "tracked").write_text("base")
    (repo / ".gitignore").write_text("ignored\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    attempt = Attempt.create(uuid4(), GitRepository(path=repo).resolve_base())
    return repo, attempt


def test_workspace_isolates_all_developer_state(tmp_path: Path) -> None:
    repo, attempt = source(tmp_path)
    (repo / "tracked").write_text("staged")
    git(repo, "add", "tracked")
    (repo / "tracked").write_text("unstaged")
    (repo / "untracked").write_text("private")
    (repo / "ignored").write_text("private ignored")
    before = git(repo, "status", "--porcelain", "--ignored")
    index = git(repo, "diff", "--cached")
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "build"
    )
    assert workspace.path == tmp_path / "build"
    assert git(workspace.path, "rev-parse", "HEAD") == attempt.start_sha
    assert (workspace.path / "tracked").read_text() == "base"
    assert not (workspace.path / "untracked").exists()
    assert not (workspace.path / "ignored").exists()
    assert git(repo, "status", "--porcelain", "--ignored") == before
    assert git(repo, "diff", "--cached") == index
    assert (repo / "tracked").read_text() == "unstaged"


def test_workspace_rejects_collisions_nested_paths_and_missing_commit(
    tmp_path: Path,
) -> None:
    repo, attempt = source(tmp_path)
    for path in (repo / "nested", repo):
        with pytest.raises(ValueError):
            GitRepository(path=repo).create_workspace(attempt=attempt, path=path)
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(ValueError):
        GitRepository(path=repo).create_workspace(attempt=attempt, path=destination)
    missing = Attempt.create(uuid4(), "a" * 40)
    with pytest.raises(ValueError):
        GitRepository(path=repo).create_workspace(
            attempt=missing, path=tmp_path / "bad"
        )


def test_candidate_is_reachable_and_independently_checkoutable(tmp_path: Path) -> None:
    repo, attempt = source(tmp_path)
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "build"
    )
    (workspace.path / "tracked").unlink()
    (workspace.path / "new").write_text("candidate")
    candidate = workspace.publish_candidate()
    assert candidate.attempt_id == attempt.attempt_id
    assert git(repo, "rev-parse", workspace.candidate_ref) == candidate.candidate_sha
    assert git(repo, "rev-parse", "HEAD") == attempt.start_sha
    independent = tmp_path / "test"
    git(repo, "worktree", "add", "--detach", str(independent), candidate.candidate_sha)
    GitRepository(path=independent).require_clean_revision(
        commit_sha=candidate.candidate_sha
    )
    assert (independent / "new").read_text() == "candidate"
    assert not (independent / "tracked").exists()
    assert (repo / "tracked").read_text() == "base"


def test_noop_candidate_and_ref_collision(tmp_path: Path) -> None:
    repo, attempt = source(tmp_path)
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "one"
    )
    first = workspace.publish_candidate()
    second = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "two"
    )
    with pytest.raises(ValueError):
        second.publish_candidate()
    assert git(repo, "rev-parse", workspace.candidate_ref) == first.candidate_sha


def test_candidate_cleans_ignored_residue_only_in_owned_workspace(
    tmp_path: Path,
) -> None:
    repo, attempt = source(tmp_path)
    (repo / "ignored").write_text("developer environment")
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "build"
    )
    (workspace.path / "ignored").mkdir()
    (workspace.path / "ignored" / "cache").write_text("BUILD residue")
    (workspace.path / "new").write_text("implementation")
    candidate = workspace.publish_candidate()
    assert not (workspace.path / "ignored").exists()
    assert (repo / "ignored").read_text() == "developer environment"
    assert git(workspace.path, "show", "HEAD:new") == "implementation"
    GitRepository(path=workspace.path).require_clean_revision(
        commit_sha=candidate.candidate_sha
    )


def test_candidate_rejects_head_drift(tmp_path: Path) -> None:
    repo, attempt = source(tmp_path)
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "build"
    )
    git(workspace.path, "switch", "-c", "unexpected")
    with pytest.raises(ValueError):
        workspace.publish_candidate()


def test_ignored_cleanup_does_not_follow_symlinks(tmp_path: Path) -> None:
    repo, attempt = source(tmp_path)
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "build"
    )
    external = tmp_path / "external-environment"
    external.mkdir()
    (external / "keep").write_text("operator data")
    (workspace.path / "ignored").symlink_to(external, target_is_directory=True)
    workspace.publish_candidate()
    assert not (workspace.path / "ignored").is_symlink()
    assert (external / "keep").read_text() == "operator data"


def test_candidate_rejects_committed_head_drift(tmp_path: Path) -> None:
    repo, attempt = source(tmp_path)
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "build"
    )
    git(workspace.path, "commit", "--allow-empty", "-m", "agent commit")
    with pytest.raises(ValueError):
        workspace.publish_candidate()
    assert git(repo, "for-each-ref", workspace.candidate_ref) == ""


def test_candidate_does_not_run_repository_hooks(tmp_path: Path) -> None:
    repo, attempt = source(tmp_path)
    hooks = repo / ".git" / "hooks"
    for name in ("post-checkout", "pre-commit", "post-commit"):
        hook = hooks / name
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
    workspace = GitRepository(path=repo).create_workspace(
        attempt=attempt, path=tmp_path / "build"
    )
    assert workspace.publish_candidate().candidate_sha
