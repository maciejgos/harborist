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
