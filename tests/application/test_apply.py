"""Application uses genuine execution captures and real Git, without a provider."""

import json
from pathlib import Path

import pytest

from shipyard.application.execution import execute_run
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture
from tests.git_helpers import git


@pytest.fixture
def packaged(
    tmp_path: Path, frozen_contract: RunContract
) -> tuple[Path, Path, RunContract, str]:
    store, repo, contract = capture(tmp_path, frozen_contract)
    evidence = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent(),
    )
    assert evidence.candidate is not None
    return (
        tmp_path / "runs",
        repo.checkout_root(),
        contract,
        evidence.candidate.candidate_sha,
    )


def test_apply_and_repeat_preserve_run(
    packaged: tuple[Path, Path, RunContract, str],
) -> None:
    from shipyard.application.apply import apply_run

    root, repo, contract, candidate = packaged
    directory = root / str(contract.run_id)
    before = {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }
    result = apply_run(
        run_id=contract.run_id, repository=repo, runs_dir=root, branch="main"
    )
    assert not result.already_applied
    assert result.receipt.resulting_sha == candidate
    assert git(repo, "rev-parse", "HEAD") == candidate
    assert (repo / "requested.txt").read_text() == "implemented"
    receipt_bytes = result.path.read_bytes()
    (repo / "requested.txt").write_text("later user edit")
    repeated = apply_run(
        run_id=contract.run_id, repository=repo, runs_dir=root, branch="main"
    )
    assert repeated.already_applied
    assert repeated.path == result.path
    assert result.path.read_bytes() == receipt_bytes
    assert (repo / "requested.txt").read_text() == "later user edit"
    assert before == {
        p.relative_to(directory): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "corruption", ["bytes", "omission", "unsafe", "conflict", "review"]
)
def test_invalid_evidence_refuses(
    packaged: tuple[Path, Path, RunContract, str], corruption: str
) -> None:
    from shipyard.application.apply import apply_run

    root, repo, contract, _ = packaged
    directory = root / str(contract.run_id)
    path = directory / "evidence.json"
    data = json.loads(path.read_text())
    if corruption == "bytes":
        (directory / "design" / "spec.md").write_text("altered")
    elif corruption == "omission":
        data["files"] = [f for f in data["files"] if f["path"] != "test/manifest.json"]
    elif corruption == "unsafe":
        data["files"][0]["path"] = "../escape"
    elif corruption == "conflict":
        data["attempt"]["start_sha"] = "f" * 40
    else:
        data["stages"][-1]["test_evidence_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        apply_run(run_id=contract.run_id, repository=repo, runs_dir=root, branch="main")
    assert git(repo, "rev-parse", "HEAD") == contract.base_sha


def test_retained_workspace_is_mutable(
    packaged: tuple[Path, Path, RunContract, str], tmp_path: Path
) -> None:
    from shipyard.application.apply import apply_run

    root, repo, contract, candidate = packaged
    (tmp_path / "work" / "requested.txt").write_text("unverified workspace edit")
    result = apply_run(
        run_id=contract.run_id, repository=repo, runs_dir=root, branch="main"
    )
    assert result.receipt.candidate_sha == candidate
    assert (repo / "requested.txt").read_text() == "implemented"


def test_receipt_failure_and_retry(
    packaged: tuple[Path, Path, RunContract, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from shipyard.application.apply import apply_run
    from shipyard.persistence.application import ApplicationStore

    root, repo, contract, candidate = packaged
    publish = ApplicationStore.publish

    def fail(self: ApplicationStore, receipt: object) -> None:
        raise OSError("disk failure")

    monkeypatch.setattr(ApplicationStore, "publish", fail)
    with pytest.raises(ValueError, match=f"Observed target SHA: {candidate}"):
        apply_run(run_id=contract.run_id, repository=repo, runs_dir=root, branch="main")
    assert git(repo, "rev-parse", "main") == candidate
    monkeypatch.setattr(ApplicationStore, "publish", publish)
    result = apply_run(
        run_id=contract.run_id, repository=repo, runs_dir=root, branch="main"
    )
    assert result.already_applied
    assert result.receipt.previous_sha == contract.base_sha
    assert result.path.is_file()


def test_preparation_failure_blocks_git(
    packaged: tuple[Path, Path, RunContract, str],
) -> None:
    from shipyard.application.apply import apply_run

    root, repo, contract, _ = packaged
    (root / "applications").write_text("obstruction")
    with pytest.raises(ValueError, match="Application failed"):
        apply_run(run_id=contract.run_id, repository=repo, runs_dir=root, branch="main")
    assert git(repo, "rev-parse", "main") == contract.base_sha


@pytest.mark.parametrize("position", ["ahead", "divergent"])
def test_target_requires_new_run(
    packaged: tuple[Path, Path, RunContract, str], position: str
) -> None:
    from shipyard.application.apply import apply_run

    root, repo, contract, candidate = packaged
    if position == "ahead":
        git(repo, "merge", "--ff-only", candidate)
    (repo / "other.txt").write_text("different")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "target changed")
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="new Run"):
        apply_run(run_id=contract.run_id, repository=repo, runs_dir=root, branch="main")
    assert git(repo, "rev-parse", "HEAD") == before


def test_omitted_test_log_is_incomplete(
    packaged: tuple[Path, Path, RunContract, str],
) -> None:
    from shipyard.application.apply import apply_run

    root, repo, contract, _ = packaged
    path = root / str(contract.run_id) / "evidence.json"
    data = json.loads(path.read_text())
    data["files"] = [
        f for f in data["files"] if f["path"] != "test/logs/0000.stdout.log"
    ]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="missing from index"):
        apply_run(run_id=contract.run_id, branch="main", repository=repo, runs_dir=root)
    assert git(repo, "rev-parse", "HEAD") == contract.base_sha


def test_unindexed_context_and_repository_conflict_are_rejected(
    packaged: tuple[Path, Path, RunContract, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shipyard.application.apply import apply_run
    from shipyard.application.context import ExecutionContext
    from tests.git_helpers import init_repository

    root, repo, contract, candidate = packaged
    ExecutionContext(
        version=1,
        run_id=contract.run_id,
        repository=repo.resolve(),
        runs_root=root.resolve(),
    ).save()
    # Adding a locator after PACKAGE must not silently change the capture.
    with pytest.raises(ValueError, match="missing from index"):
        apply_run(run_id=contract.run_id, branch="main", runs_dir=root)
    other = tmp_path / "elsewhere"
    init_repository(other)
    monkeypatch.chdir(other)
    with pytest.raises(ValueError, match="Conflicting --repo"):
        apply_run(
            run_id=contract.run_id, branch="main", repository=other, runs_dir=root
        )
    assert git(repo, "rev-parse", "main") == contract.base_sha
    assert candidate != contract.base_sha
