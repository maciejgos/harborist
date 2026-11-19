"""Application uses genuine execution captures and real Git, without a provider."""

import json
from pathlib import Path

import pytest

from harborist.application.execution import execute_run
from harborist.domain import RunContract
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
    from harborist.application.apply import apply_run

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
    from harborist.application.apply import apply_run

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
    from harborist.application.apply import apply_run

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
    from harborist.application.apply import apply_run
    from harborist.persistence.application import ApplicationStore

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
    from harborist.application.apply import apply_run

    root, repo, contract, _ = packaged
    (root / "applications").write_text("obstruction")
    with pytest.raises(ValueError, match="Application failed"):
        apply_run(run_id=contract.run_id, repository=repo, runs_dir=root, branch="main")
    assert git(repo, "rev-parse", "main") == contract.base_sha


@pytest.mark.parametrize("position", ["ahead", "divergent"])
def test_target_requires_new_run(
    packaged: tuple[Path, Path, RunContract, str], position: str
) -> None:
    from harborist.application.apply import apply_run

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
    from harborist.application.apply import apply_run

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
    from harborist.application.apply import apply_run
    from harborist.application.context import ExecutionContext
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


def test_publication_rejects_wrong_approval_and_moved_candidate_ref(
    packaged: tuple[Path, Path, RunContract, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from harborist.application import publication

    root, repo, contract, candidate = packaged
    run_id = contract.run_id
    monkeypatch.chdir(repo)

    def unexpected_api(endpoint: str) -> object:
        pytest.fail(
            f"Publication contacted GitHub before validating evidence: {endpoint}"
        )

    monkeypatch.setattr(publication, "api", unexpected_api)
    with pytest.raises(ValueError, match="Approval must match"):
        publication.publish_run(
            run_id,
            approve=contract.base_sha,
            destination="owner/repo",
            base="main",
            runs_dir=root,
        )
    with pytest.raises(ValueError, match="previous Attempt"):
        publication.publish_run(
            run_id,
            approve=candidate,
            expected_attempt=run_id,
            destination="owner/repo",
            base="main",
            runs_dir=root,
        )
    git(repo, "update-ref", f"refs/shipyard/runs/{run_id}/candidate", contract.base_sha)
    with pytest.raises(ValueError, match="candidate ref does not match"):
        publication.publish_run(
            run_id,
            approve=candidate,
            destination="owner/repo",
            base="main",
            runs_dir=root,
        )


def test_selected_github_review_starts_fresh_verification(
    packaged: tuple[Path, Path, RunContract, str],
) -> None:
    from datetime import UTC, datetime

    from harborist.application.collaboration import Observation
    from harborist.application.publication import publication_directory
    from harborist.domain import RunOutcome
    from harborist.domain.continuation import (
        ContinuationRequest,
        GitHubFeedbackSelection,
    )
    from harborist.git.repository import GitRepository
    from harborist.github.collaboration import CheckPage, Feedback, StatusPage
    from harborist.persistence import FileRunStore
    from harborist.persistence.continuation import prepare_continuation

    root, repo, contract, candidate = packaged
    run_id = contract.run_id
    store = FileRunStore(root=root)
    verification = store.load_state(run_id).verification
    assert verification is not None
    directory = publication_directory(root, run_id) / "observations"
    directory.mkdir(parents=True)
    path = directory / "example.json"
    path.write_text(
        Observation(
            run_id=run_id,
            repository="owner/repo",
            observed_at=datetime.now(UTC),
            pull=1,
            url="https://github.com/owner/repo/pull/1",
            state="open",
            head="a" * 40,
            verified_candidate=candidate,
            head_verified=False,
            merged_at=None,
            merge_commit_sha=None,
            checks=CheckPage(total_count=0, check_runs=()),
            statuses=StatusPage(state="pending", total_count=0, statuses=()),
            feedback=(
                Feedback(key="review:1", author="reviewer", body="Selected feedback"),
                Feedback(key="review:2", author="reviewer", body="Excluded feedback"),
            ),
        ).model_dump_json()
    )
    selected, record = prepare_continuation(
        store=store,
        run_id=run_id,
        request=ContinuationRequest(
            action="rework",
            expected_attempt_id=verification.attempt.attempt_id,
            github_feedback=GitHubFeedbackSelection(
                observation=path, ids=("review:1",)
            ),
        ),
    )
    assert record.attempt.start_sha == candidate
    assert record.attempt.attempt_id != verification.attempt.attempt_id
    context = json.loads(
        (selected.directory(run_id) / "continuation-context.json").read_text()
    )
    assert "Selected feedback" in context["feedback"]
    assert "Excluded feedback" not in context["feedback"]
    evidence = execute_run(
        store=selected,
        run_id=run_id,
        repository=GitRepository(path=repo),
        workspace=root.parent / "rework",
        agent=FakeAgent(),
    )
    assert evidence.run.outcome == RunOutcome.VERIFIED
    assert evidence.attempt == record.attempt
    assert evidence.test is not None


def test_publication_pushes_exact_candidate_and_reconciles_retry(
    packaged: tuple[Path, Path, RunContract, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harborist.application import publication
    from harborist.git.publication import push_candidate

    root, repo, contract, candidate = packaged
    monkeypatch.chdir(repo)
    remote = root.parent / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    git(repo, "push", str(remote), f"{contract.base_sha}:refs/heads/main")
    branch = f"harborist/{contract.run_id}"
    ref = f"refs/heads/{branch}"
    run_git = publication.run_git
    pulls: list[dict[str, object]] = []

    def redirected_git(path: Path, *args: str) -> bytes:
        return run_git(
            path,
            *(
                str(remote) if arg == "https://github.com/owner/repo.git" else arg
                for arg in args
            ),
        )

    def redirected_push(
        path: Path, url: str, ref: str, candidate: str, previous: str | None
    ) -> None:
        assert url == "https://github.com/owner/repo.git"
        push_candidate(path, str(remote), ref, candidate, previous)

    def api(endpoint: str, *, payload: dict[str, str] | None = None) -> object:
        assert endpoint.startswith("repos/owner/repo/pulls")
        if payload is None:
            return pulls
        assert git(remote, "rev-parse", ref) == candidate
        assert candidate in payload["body"]
        pulls.append(
            {
                "number": 17,
                "html_url": "https://github.com/owner/repo/pull/17",
                "state": "open",
                "head": {"ref": branch, "sha": candidate},
                "base": {"ref": "main", "sha": contract.base_sha},
                "body": payload["body"],
            }
        )
        return pulls[-1]

    monkeypatch.setattr(publication, "run_git", redirected_git)
    monkeypatch.setattr(publication, "push_candidate", redirected_push)
    monkeypatch.setattr(publication, "api", api)
    for _ in range(2):
        result = publication.publish_run(
            contract.run_id,
            approve=candidate,
            destination="owner/repo",
            base="main",
            runs_dir=root,
        )
        assert result.number == 17
    assert len(pulls) == 1
