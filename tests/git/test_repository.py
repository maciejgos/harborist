"""Resolve real committed state without changing the repository."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from shipyard.git import GitReadError, GitRepository, GitResolutionError
from shipyard.verification import (
    VerificationConfigError,
    load_verification_config,
)
from tests.git_helpers import git, init_repository


@pytest.fixture
def repository_path(tmp_path: Path) -> Path:
    path = tmp_path / "repository with spaces"
    init_repository(path)
    tracked = path / "tracked.txt"
    tracked.write_bytes(b"First version")
    git(path, "add", "tracked.txt")
    git(path, "commit", "-m", "First commit")
    tracked.write_bytes(b"Second version")
    git(path, "add", "tracked.txt")
    git(path, "commit", "-m", "Second commit")
    return path


def test_constructor_performs_no_io(tmp_path: Path) -> None:
    path = tmp_path / "not-created"
    GitRepository(path=path)
    assert not path.exists()


def test_default_head_and_explicit_branch(repository_path: Path) -> None:
    repository = GitRepository(path=repository_path)
    expected = git(repository_path, "rev-parse", "HEAD")
    assert repository.resolve_base() == expected
    assert repository.resolve_base(ref="main") == expected


def test_native_hashes_ancestor_and_annotated_tag(repository_path: Path) -> None:
    repository = GitRepository(path=repository_path)
    head = git(repository_path, "rev-parse", "HEAD")
    parent = git(repository_path, "rev-parse", "HEAD~1")
    git(repository_path, "tag", "-a", "release", parent, "-m", "Release")
    assert repository.resolve_base(ref=head) == head
    assert repository.resolve_base(ref=head[:12]) == head
    assert repository.resolve_base(ref="HEAD~1") == parent
    assert repository.resolve_base(ref="release") == parent


def test_detached_head_and_subdirectory(repository_path: Path) -> None:
    git(repository_path, "checkout", "--detach", "HEAD~1")
    nested = repository_path / "nested"
    nested.mkdir()
    assert GitRepository(path=nested).resolve_base() == git(
        repository_path, "rev-parse", "HEAD"
    )


def test_bare_repository(repository_path: Path, tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    git(repository_path, "clone", "--bare", str(repository_path), str(bare))
    assert GitRepository(path=bare).resolve_base() == git(
        repository_path, "rev-parse", "HEAD"
    )


def test_sha256_repository(tmp_path: Path) -> None:
    path = tmp_path / "sha256"
    init_repository(path, object_format="sha256")
    git(path, "commit", "--allow-empty", "-m", "SHA-256 commit")
    resolved = GitRepository(path=path).resolve_base()
    assert len(resolved) == 64
    assert resolved == git(path, "rev-parse", "HEAD")


def test_saved_sha_does_not_follow_advancing_branch(repository_path: Path) -> None:
    repository = GitRepository(path=repository_path)
    before = repository.resolve_base(ref="main")
    git(repository_path, "commit", "--allow-empty", "-m", "Advance main")
    after = repository.resolve_base(ref="main")
    assert before != after
    assert before == git(repository_path, "rev-parse", "HEAD~1")
    assert after == git(repository_path, "rev-parse", "HEAD")


def test_dirty_developer_state_remains_unchanged(repository_path: Path) -> None:
    tracked = repository_path / "tracked.txt"
    tracked.write_bytes(b"Staged version")
    git(repository_path, "add", "tracked.txt")
    tracked.write_bytes(b"Unstaged version")
    untracked = repository_path / "untracked.txt"
    untracked.write_bytes(b"Keep untracked content")
    index = repository_path / ".git" / "index"
    before_index = index.read_bytes()
    before_head = git(repository_path, "rev-parse", "HEAD")
    before_branch = git(repository_path, "symbolic-ref", "HEAD")
    resolved = GitRepository(path=repository_path).resolve_base()
    assert resolved == before_head
    assert git(repository_path, "symbolic-ref", "HEAD") == before_branch
    assert index.read_bytes() == before_index
    assert tracked.read_bytes() == b"Unstaged version"
    assert untracked.read_bytes() == b"Keep untracked content"


@pytest.mark.parametrize(
    "ref", ["missing-ref", "", "HEAD^{tree}", "HEAD..HEAD", "--help"]
)
def test_invalid_commit_inputs(repository_path: Path, ref: str) -> None:
    with pytest.raises(GitResolutionError) as caught:
        GitRepository(path=repository_path).resolve_base(ref=ref)
    assert str(repository_path) in str(caught.value)
    assert repr(ref) in str(caught.value)
    if ref:
        assert isinstance(caught.value.__cause__, subprocess.CalledProcessError)
    else:
        assert caught.value.__cause__ is None


def test_unborn_head(tmp_path: Path) -> None:
    path = tmp_path / "unborn"
    init_repository(path)
    with pytest.raises(GitResolutionError) as caught:
        GitRepository(path=path).resolve_base()
    assert isinstance(caught.value.__cause__, subprocess.CalledProcessError)


def test_supplied_repository_ignores_inherited_redirection(
    repository_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "other"
    init_repository(other)
    git(other, "commit", "--allow-empty", "-m", "Different repository")
    expected = git(repository_path, "rev-parse", "HEAD")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_COMMON_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(other / ".git" / "objects"))
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "1")
    before_environment = dict(os.environ)
    assert GitRepository(path=repository_path).resolve_base() == expected
    assert dict(os.environ) == before_environment


@pytest.mark.parametrize("exists", [False, True])
def test_missing_or_non_repository_path(tmp_path: Path, exists: bool) -> None:
    path = tmp_path / "not-a-repository"
    if exists:
        path.mkdir()
    with pytest.raises(GitResolutionError) as caught:
        GitRepository(path=path).resolve_base()
    assert isinstance(caught.value.__cause__, subprocess.CalledProcessError)


def test_missing_git_preserves_launch_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = FileNotFoundError("Git is not installed")

    def missing_git(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        raise error

    monkeypatch.setattr("shipyard.git.command.subprocess.run", missing_git)
    with pytest.raises(GitResolutionError) as caught:
        GitRepository(path=tmp_path).resolve_base()
    assert caught.value.__cause__ is error
    assert str(tmp_path) in str(caught.value)
    assert "HEAD" in str(caught.value)


@pytest.mark.parametrize(
    "stdout,cause",
    [
        (b"not-a-sha\n", ValidationError),
        (b"a" * 40 + b"\n" + b"b" * 40, ValidationError),
        (b"\xff", UnicodeDecodeError),
    ],
)
def test_malformed_successful_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes,
    cause: type[Exception],
) -> None:
    def malformed_git(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout=stdout, stderr=b""
        )

    monkeypatch.setattr("shipyard.git.command.subprocess.run", malformed_git)
    with pytest.raises(GitResolutionError) as caught:
        GitRepository(path=tmp_path).resolve_base()
    assert isinstance(caught.value.__cause__, cause)


def test_subprocess_environment_preserves_configuration_without_repo_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overrides = (
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
    for name in overrides:
        monkeypatch.setenv(name, "caller-repository-override")
    monkeypatch.setenv("GIT_OPTIONAL_LOCKS", "1")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.abbrev")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "12")
    calls = 0

    def inspect_git(
        args: list[str], *, check: bool, capture_output: bool, env: dict[str, str]
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        assert check and capture_output
        assert args[-2:] == ["--end-of-options", "HEAD^{commit}"]
        assert all(name not in env for name in overrides)
        assert env["GIT_OPTIONAL_LOCKS"] == "0"
        assert env["GIT_CONFIG_COUNT"] == "1"
        assert env["GIT_CONFIG_KEY_0"] == "core.abbrev"
        assert env["GIT_CONFIG_VALUE_0"] == "12"
        assert env["PATH"] == os.environ["PATH"]
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=b"a" * 40 + b"\n", stderr=b""
        )

    monkeypatch.setattr("shipyard.git.command.subprocess.run", inspect_git)
    assert GitRepository(path=tmp_path).resolve_base() == "a" * 40
    assert calls == 1
    assert all(os.environ[name] == "caller-repository-override" for name in overrides)
    assert os.environ["GIT_OPTIONAL_LOCKS"] == "1"


def test_read_file_uses_exact_commit_and_root_relative_path(
    repository_path: Path,
) -> None:
    nested = repository_path / "nested"
    nested.mkdir()
    repository = GitRepository(path=nested)
    base = repository.resolve_base(ref="HEAD~1")
    (repository_path / "tracked.txt").write_bytes(b"Checkout must not be read")
    assert (
        repository.read_file_at_commit(commit_sha=base, path="./tracked.txt")
        == b"First version"
    )


@pytest.mark.parametrize("path", ["missing.yaml", ""])
def test_read_file_rejects_missing_or_non_blob_path(
    repository_path: Path, path: str
) -> None:
    repository = GitRepository(path=repository_path)
    with pytest.raises(GitReadError) as caught:
        repository.read_file_at_commit(commit_sha=repository.resolve_base(), path=path)
    assert repr(path) in str(caught.value)
    assert caught.value.__cause__ is not None


def test_read_file_rejects_directory_target(repository_path: Path) -> None:
    directory = repository_path / "config"
    directory.mkdir()
    (directory / "file").write_bytes(b"data")
    git(repository_path, "add", "config")
    git(repository_path, "commit", "-m", "Directory target")
    repository = GitRepository(path=repository_path)
    with pytest.raises(GitReadError):
        repository.read_file_at_commit(
            commit_sha=repository.resolve_base(), path="config"
        )


def test_read_file_requires_commit_identity_without_tag_peeling(
    repository_path: Path,
) -> None:
    repository = GitRepository(path=repository_path)
    with pytest.raises(ValidationError):
        repository.read_file_at_commit(commit_sha="main", path="tracked.txt")
    git(repository_path, "tag", "-a", "tag-object", "-m", "Annotated")
    tag_sha = git(repository_path, "rev-parse", "tag-object")
    with pytest.raises(GitReadError):
        repository.read_file_at_commit(commit_sha=tag_sha, path="tracked.txt")


@pytest.mark.parametrize("path", ["/tracked.txt", "../tracked.txt"])
def test_read_file_rejects_paths_outside_repository(
    repository_path: Path, path: str
) -> None:
    repository = GitRepository(path=repository_path)
    with pytest.raises(GitReadError):
        repository.read_file_at_commit(commit_sha=repository.resolve_base(), path=path)


def test_verification_snapshot_ignores_checkout_and_later_commits(
    repository_path: Path,
) -> None:
    source = b"version: 1\nchecks:\n  - id: tests\n    command: pytest\n"
    path = repository_path / "shipyard.yaml"
    path.write_bytes(source)
    git(repository_path, "add", "shipyard.yaml")
    git(repository_path, "commit", "-m", "Committed verification config")
    repository = GitRepository(path=repository_path)
    base = repository.resolve_base()
    snapshot = load_verification_config(repository=repository, base_sha=base)
    serialized = snapshot.model_dump_json()
    assert snapshot.base_sha == base
    assert snapshot.source_sha256 == hashlib.sha256(source).hexdigest()
    path.write_bytes(b"version: 1\nchecks: [{id: tests, command: staged-command}]\n")
    git(repository_path, "add", "shipyard.yaml")
    path.write_bytes(b"Invalid uncommitted configuration")
    index = repository_path / ".git" / "index"
    before_index = index.read_bytes()
    assert (
        load_verification_config(repository=repository, base_sha=base).model_dump_json()
        == serialized
    )
    assert index.read_bytes() == before_index
    assert path.read_bytes() == b"Invalid uncommitted configuration"
    git(repository_path, "commit", "-m", "Change committed command")
    assert repository.resolve_base() != base
    assert snapshot.model_dump_json() == serialized
    assert (
        load_verification_config(repository=repository, base_sha=base).model_dump_json()
        == serialized
    )
    newer = load_verification_config(
        repository=repository, base_sha=repository.resolve_base()
    )
    assert newer.config.checks[0].command == "staged-command"
    assert snapshot.config.checks[0].command == "pytest"


def test_verification_source_digest_captures_yaml_formatting(
    repository_path: Path,
) -> None:
    path = repository_path / "shipyard.yaml"
    path.write_bytes(b"version: 1\nchecks: [{id: tests, command: pytest}]\n")
    git(repository_path, "add", "shipyard.yaml")
    git(repository_path, "commit", "-m", "Initial config")
    repository = GitRepository(path=repository_path)
    before = load_verification_config(
        repository=repository, base_sha=repository.resolve_base()
    )
    path.write_bytes(path.read_bytes() + b"# formatting provenance\n")
    git(repository_path, "add", "shipyard.yaml")
    git(repository_path, "commit", "-m", "Add config comment")
    after = load_verification_config(
        repository=repository, base_sha=repository.resolve_base()
    )
    assert after.config == before.config
    assert after.source_sha256 != before.source_sha256
    assert after.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_verification_reads_original_commit_despite_git_replacement(
    repository_path: Path,
) -> None:
    path = repository_path / "shipyard.yaml"
    path.write_bytes(b"version: 1\nchecks: [{id: tests, command: original-check}]\n")
    git(repository_path, "add", "shipyard.yaml")
    git(repository_path, "commit", "-m", "Original base")
    repository = GitRepository(path=repository_path)
    base = repository.resolve_base()
    path.write_bytes(b"version: 1\nchecks: [{id: tests, command: replacement-check}]\n")
    git(repository_path, "add", "shipyard.yaml")
    git(repository_path, "commit", "-m", "Replacement commit")
    replacement = repository.resolve_base()
    git(repository_path, "replace", base, replacement)
    snapshot = load_verification_config(repository=repository, base_sha=base)
    assert snapshot.base_sha == base
    assert snapshot.config.checks[0].command == "original-check"


@pytest.mark.parametrize(
    "failure", ["missing", "nonexistent-commit", "directory", "invalid-config"]
)
def test_configuration_load_failures_include_base_context(
    repository_path: Path, failure: str
) -> None:
    path = repository_path / "shipyard.yaml"
    if failure == "directory":
        path.mkdir()
        (path / "nested").write_bytes(b"not a config file")
    elif failure == "invalid-config":
        path.write_bytes(b"version: 2\nchecks: []\n")
    if path.exists():
        git(repository_path, "add", "shipyard.yaml")
        git(repository_path, "commit", "-m", "Invalid config target")
    repository = GitRepository(path=repository_path)
    base = "0" * 40 if failure == "nonexistent-commit" else repository.resolve_base()
    with pytest.raises(VerificationConfigError) as caught:
        load_verification_config(repository=repository, base_sha=base)
    assert base in str(caught.value)
    assert "shipyard.yaml" in str(caught.value)
    assert caught.value.__cause__ is not None
