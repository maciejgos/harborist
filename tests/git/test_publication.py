import subprocess
from pathlib import Path

import pytest

from harborist.git.publication import expected_head, push_candidate
from tests.git_helpers import git, init_repository


def test_stale_head_cannot_be_replaced() -> None:
    with pytest.raises(ValueError, match="head changed"):
        expected_head(observed="human", previous="published", candidate="verified")


def test_partial_publication_can_be_reconciled() -> None:
    assert expected_head(
        observed="verified", previous="published", candidate="verified"
    )
    assert not expected_head(observed=None, previous=None, candidate="verified")


def test_push_lease_preserves_a_concurrently_changed_remote(tmp_path: Path) -> None:
    local = tmp_path / "local"
    init_repository(local)
    git(local, "commit", "--allow-empty", "-m", "base")
    base = git(local, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    ref = "refs/heads/harborist/run"
    push_candidate(local, str(remote), ref, base, None)
    git(local, "commit", "--allow-empty", "-m", "approved")
    approved = git(local, "rev-parse", "HEAD")
    git(local, "commit", "--allow-empty", "-m", "human change")
    human = git(local, "rev-parse", "HEAD")
    push_candidate(local, str(remote), ref, human, base)
    with pytest.raises(subprocess.CalledProcessError):
        push_candidate(local, str(remote), ref, approved, base)
    assert git(remote, "rev-parse", ref) == human
