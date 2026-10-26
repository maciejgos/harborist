"""Phase 2 acceptance across real Git, source files and filesystem storage."""

import json
import os
import sys
from pathlib import Path

import pytest

from shipyard.application import create_run
from shipyard.domain import GitCommitSha, Run, RunLifecycle
from shipyard.domain.execution import ExecutionSnapshot
from shipyard.git import GitRepository
from shipyard.persistence import (
    FileRunStore,
    RunAlreadyExistsError,
)
from shipyard.verification import VerificationConfigError
from tests.git_helpers import git, init_repository


@pytest.fixture
def target(tmp_path: Path) -> Path:
    path = tmp_path / "target"
    init_repository(path)
    (path / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: tests, command: pytest}]\n"
    )
    git(path, "add", "shipyard.yaml")
    git(path, "commit", "-m", "Base configuration")
    return path


def test_create_freezes_once_and_survives_all_mutable_inputs(
    tmp_path: Path,
    target: Path,
    execution: ExecutionSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"\xef\xbb\xbf---\r\npriority: high\r\n---\r\nFix it\r\n")
    store = FileRunStore(root=tmp_path / "runs")
    run = Run.create()
    repository = GitRepository(path=target)
    base = repository.resolve_base()
    (target / "shipyard.yaml").write_text("invalid uncommitted configuration")
    index = target / ".git" / "index"
    before_index = index.read_bytes()
    original_resolve = repository.resolve_base
    resolved: list[str] = []

    def resolve_once(*, ref: str = "HEAD") -> GitCommitSha:
        resolved.append(ref)
        return original_resolve(ref=ref)

    monkeypatch.setattr(repository, "resolve_base", resolve_once)
    contract = create_run(
        source=f"file:{source}",
        repository=repository,
        store=store,
        execution=execution,
        run=run,
    )
    assert contract.base_sha == base
    assert resolved == ["HEAD"]
    assert index.read_bytes() == before_index
    assert contract.verification.config.checks[0].command == "pytest"
    assert store.load(run.run_id) == contract
    directory = tmp_path / "runs" / str(run.run_id)
    assert (
        Run.model_validate_json((directory / "run.json").read_bytes()).lifecycle
        == RunLifecycle.CREATED
    )
    assert (directory / "intent.md").read_bytes() == source.read_bytes()
    before = (directory / "contract.json").read_bytes()
    source.unlink()
    (target / "shipyard.yaml").write_text("invalid checkout settings")
    git(target, "commit", "--allow-empty", "-m", "Advance base")
    assert store.load(run.run_id).model_dump_json().encode() == before
    with pytest.raises(RunAlreadyExistsError):
        store.save(contract)
    assert (directory / "contract.json").read_bytes() == before


def test_same_captured_inputs_produce_identical_contracts(
    tmp_path: Path,
    target: Path,
    execution: ExecutionSnapshot,
) -> None:
    issue = tmp_path / "issue.md"
    issue.write_text("Request")
    run = Run.create()
    repository = GitRepository(path=target)
    first = create_run(
        source=f"file:{issue}",
        repository=repository,
        store=FileRunStore(root=tmp_path / "one"),
        execution=execution,
        run=run,
    )
    # Intake generates artifact IDs. Reusing the frozen capture, rather than
    # recapturing the source, is what defines equivalent frozen input.
    second = type(first).model_validate(
        dict(reversed(list(first.model_dump().items())))
    )
    store = FileRunStore(root=tmp_path / "two")
    store.save(second)
    assert store.load(run.run_id).model_dump_json() == first.model_dump_json()


def test_invalid_base_configuration_never_publishes_contract(
    tmp_path: Path,
    target: Path,
    execution: ExecutionSnapshot,
) -> None:
    (target / "shipyard.yaml").write_text("invalid")
    git(target, "add", "shipyard.yaml")
    git(target, "commit", "-m", "Bad config")
    root = tmp_path / "runs"
    with pytest.raises(VerificationConfigError):
        create_run(
            source="file:unused.md",
            repository=GitRepository(path=target),
            store=FileRunStore(root=root),
            execution=execution,
        )
    assert not root.exists()


def test_noncreated_run_is_rejected_before_io(
    tmp_path: Path, execution: ExecutionSnapshot
) -> None:
    with pytest.raises(ValueError, match="CREATED"):
        create_run(
            source="file:unused",
            repository=GitRepository(path=tmp_path),
            store=FileRunStore(root=tmp_path / "runs"),
            execution=execution,
            run=Run.create().start(),
        )
    assert not (tmp_path / "runs").exists()


def test_github_capture_is_durable_after_issue_edit(
    tmp_path: Path,
    target: Path,
    execution: ExecutionSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = tmp_path / "response.json"
    response.write_text(
        json.dumps(
            {"title": "Original", "body": "Original body", "labels": [{"name": "bug"}]}
        )
    )
    executable = tmp_path / "gh"
    executable.write_text(
        f"#!{sys.executable}\nfrom pathlib import Path\nprint(Path({str(response)!r}).read_text())\n"
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    store = FileRunStore(root=tmp_path / "runs")
    contract = create_run(
        source="github:independent/source#42",
        repository=GitRepository(path=target),
        store=store,
        execution=execution,
    )
    frozen = contract.model_dump_json()
    response.write_text(
        json.dumps({"title": "Edited", "body": "Different", "labels": []})
    )
    executable.unlink()
    assert store.load(contract.run_id).model_dump_json() == frozen
    assert contract.intent.markdown == '# Original\n\nLabels: ["bug"]\n\nOriginal body'


def test_explicit_ref_selects_older_committed_settings(
    tmp_path: Path, target: Path, execution: ExecutionSnapshot
) -> None:
    issue = tmp_path / "issue.md"
    issue.write_text("Request")
    original = GitRepository(path=target).resolve_base()
    (target / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: tests, command: changed}]\n"
    )
    git(target, "add", "shipyard.yaml")
    git(target, "commit", "-m", "New checks")
    contract = create_run(
        source=f"file:{issue}",
        repository=GitRepository(path=target),
        store=FileRunStore(root=tmp_path / "runs"),
        execution=execution,
        ref="HEAD~1",
    )
    assert contract.base_sha == original
    assert contract.verification.config.checks[0].command == "pytest"
