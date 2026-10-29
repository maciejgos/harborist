"""Run-owned storage policy exercised through real filesystem and Git boundaries."""

import json
from os import stat_result
from pathlib import Path
from uuid import uuid4

import pytest

from shipyard.agents.base import AgentRequest, AgentResponse
from shipyard.application import create_run
from shipyard.application.execution import execute_run
from shipyard.domain import RunContract, RunOutcome
from shipyard.domain.stage_result import AgentStage
from shipyard.persistence import FileRunStore
from tests.application.test_run_execution import FakeAgent, capture
from tests.git_helpers import git


def test_nested_workspace_identity_cleanup_and_evidence(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shipyard.application import intake

    def no_recapture(*args: object, **kwargs: object) -> None:
        pytest.fail("execution must not recapture intent")

    monkeypatch.setattr(intake, "create_run", no_recapture)
    store, repo, contract = capture(
        tmp_path,
        frozen_contract,
        "mkdir .pytest_cache && touch .pytest_cache/check && test -f requested.txt",
    )
    directory = store.directory(contract.run_id)
    marker = json.loads((directory / "workspace-layout.json").read_text())
    assert marker == {
        "version": 1,
        "run_id": str(contract.run_id),
        "layout": "run-owned",
    }
    sentinel = directory / "operator.log"
    sentinel.write_bytes(b"retained sibling evidence")
    sibling_cache = directory / ".pytest_cache"
    sibling_cache.mkdir()
    (sibling_cache / "keep").write_text("sibling cache evidence")
    source_before = git(tmp_path / "repository", "status", "--porcelain", "--ignored")
    requests: list[AgentRequest] = []

    class NestedAgent(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            requests.append(request)
            response = super().execute(request)
            if request.stage == AgentStage.BUILD:
                (request.workspace / "link").symlink_to("requested.txt")
            return response

    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        agent=NestedAgent("caches"),
    )
    workspace = (directory / "workspace").resolve()
    assert result.run.outcome == RunOutcome.VERIFIED
    assert result.workspace == workspace
    assert all(r.workspace == workspace for r in requests)
    assert result.attempt is not None and result.attempt.run_id == contract.run_id
    assert result.candidate is not None
    assert result.candidate.attempt_id == result.attempt.attempt_id
    assert result.contract == contract == store.load(contract.run_id)
    association = json.loads((directory / "execution-workspace.json").read_text())
    assert association["run_id"] == str(contract.run_id)
    assert association["attempt_id"] == str(result.attempt.attempt_id)
    assert association["path"] == str(workspace)
    assert sentinel.read_bytes() == b"retained sibling evidence"
    assert not (workspace / ".venv").exists()
    assert not (workspace / ".pytest_cache").exists()
    assert (sibling_cache / "keep").read_text() == "sibling cache evidence"
    assert not any(f.path.startswith("workspace/") for f in result.files)
    assert git(workspace, "ls-files", "operator.log", "contract.json") == ""
    assert (
        git(tmp_path / "repository", "status", "--porcelain", "--ignored")
        == source_before
    )
    assert str(workspace) in (directory / "report.md").read_text()
    assert json.loads((directory / "evidence.json").read_text())["workspace"] == str(
        workspace
    )
    before = (directory / "evidence.json").read_bytes()
    (workspace / "requested.txt").write_text("operator edits retained checkout")
    assert (directory / "evidence.json").read_bytes() == before


@pytest.mark.parametrize(
    "kind",
    [
        "stage",
        "other-run",
        "other-storage",
        "ancestor",
        "dangling-parent",
        "collision",
        "permission",
    ],
)
def test_invalid_placements_remain_created(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    directory = store.directory(contract.run_id)
    workspace = directory / "design" / "checkout"
    if kind == "other-run":
        workspace = directory.parent / str(uuid4()) / "workspace"
    elif kind == "other-storage":
        other = FileRunStore(root=tmp_path / "other-storage")
        other.save(contract)
        workspace = other.directory(contract.run_id) / "design" / "checkout"
    elif kind == "ancestor":
        workspace = directory.parent.parent
    elif kind == "dangling-parent":
        parent = tmp_path / "dangling"
        parent.symlink_to(tmp_path / "absent", target_is_directory=True)
        workspace = parent / "checkout"
    elif kind == "collision":
        workspace = directory / "workspace"
        workspace.mkdir()
        (workspace / "keep").write_text("retained")
    elif kind == "permission":
        from shipyard.git import repository

        workspace = directory / "workspace"

        def denied(*args: object) -> bool:
            return False

        monkeypatch.setattr(repository.os, "access", denied)
    before = (directory / "contract.json").read_bytes()
    agent = FakeAgent()
    with pytest.raises(ValueError, match="--workspace") as error:
        execute_run(
            store=store,
            run_id=contract.run_id,
            repository=repo,
            workspace=workspace,
            agent=agent,
        )
    assert str(workspace) in str(error.value)
    assert store.load_state(contract.run_id).lifecycle.value == "CREATED"
    assert not (directory / ".execution").exists()
    assert agent.calls == []
    assert (directory / "contract.json").read_bytes() == before
    if kind == "collision":
        assert (workspace / "keep").read_text() == "retained"


def test_in_source_runs_default_rejected_external_override_works(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    _, repo, contract = capture(tmp_path, frozen_contract)
    store = FileRunStore(root=tmp_path / "repository" / "runs")
    store.save(contract)
    agent = FakeAgent("clarify")
    with pytest.raises(ValueError, match="--workspace"):
        execute_run(store=store, run_id=contract.run_id, repository=repo, agent=agent)
    assert not agent.calls
    assert store.load_state(contract.run_id).lifecycle.value == "CREATED"
    external = tmp_path / "external"
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=external,
        agent=agent,
    )
    assert result.workspace == external.resolve()


@pytest.mark.parametrize("override", [False, True])
def test_legacy_created_selection(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    override: bool,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    store, repo, contract = capture(tmp_path, frozen_contract)
    directory = store.directory(contract.run_id)
    (directory / "workspace-layout.json").unlink()
    expected = (
        tmp_path / "override"
        if override
        else tmp_path / "home" / ".shipyard" / "workspaces" / str(contract.run_id)
    )
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=expected if override else None,
        agent=FakeAgent("clarify"),
    )
    assert result.workspace == expected.resolve()
    assert not (directory / "workspace-layout.json").exists()


@pytest.mark.parametrize("damage", ["version", "identity", "malformed"])
def test_invalid_layout_fails_closed(
    tmp_path: Path, frozen_contract: RunContract, damage: str
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    marker = store.directory(contract.run_id) / "workspace-layout.json"
    data = {
        "version": 2 if damage == "version" else 1,
        "run_id": str(uuid4()) if damage == "identity" else str(contract.run_id),
        "layout": "run-owned",
    }
    marker.write_text("{" if damage == "malformed" else json.dumps(data))
    agent = FakeAgent()
    with pytest.raises(ValueError):
        execute_run(store=store, run_id=contract.run_id, repository=repo, agent=agent)
    assert not agent.calls
    assert not (marker.parent / ".execution").exists()


def test_identical_captures_keep_distinct_identity(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, _ = capture(tmp_path, frozen_contract)
    source = tmp_path / "identical.md"
    source.write_text("Same explicit intake")
    first, second = [
        create_run(
            source=f"file:{source}",
            repository=repo,
            store=store,
            execution=frozen_contract.execution,
        )
        for _ in range(2)
    ]
    assert first.run_id != second.run_id
    results = [
        execute_run(
            store=store, run_id=c.run_id, repository=repo, agent=FakeAgent("clarify")
        )
        for c in (first, second)
    ]
    assert first.intent.artifact.sha256 == second.intent.artifact.sha256
    assert results[0].workspace != results[1].workspace
    assert all(
        r.workspace == store.directory(r.run.run_id).resolve() / "workspace"
        for r in results
    )


@pytest.mark.parametrize("override", [False, True])
def test_recorded_legacy_selection_remains_authoritative_and_immutable(
    tmp_path: Path, frozen_contract: RunContract, override: bool
) -> None:
    from shipyard.persistence.workspace import WorkspaceSelection

    store, repo, contract = capture(tmp_path, frozen_contract)
    directory = store.directory(contract.run_id)
    (directory / "workspace-layout.json").unlink()
    recorded = tmp_path / "historical-selected"
    path = directory / "workspace.json"
    path.write_text(
        WorkspaceSelection(
            run_id=contract.run_id, attempt_id=uuid4(), path=recorded
        ).model_dump_json()
    )
    before = path.read_bytes()
    selected = tmp_path / "explicit" if override else recorded
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=selected if override else None,
        agent=FakeAgent("clarify"),
    )
    assert result.workspace == selected
    assert selected.is_dir()
    assert path.read_bytes() == before


def test_legacy_existing_worktree_is_retained_before_admission(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shipyard.domain import Attempt

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    store, repo, contract = capture(tmp_path, frozen_contract)
    directory = store.directory(contract.run_id)
    (directory / "workspace-layout.json").unlink()
    destination = tmp_path / "home" / ".shipyard" / "workspaces" / str(contract.run_id)
    repo.create_workspace(
        attempt=Attempt.create(contract.run_id, contract.base_sha), path=destination
    )
    (destination / "keep").write_text("retained")
    agent = FakeAgent()
    with pytest.raises(ValueError, match="--workspace"):
        execute_run(store=store, run_id=contract.run_id, repository=repo, agent=agent)
    assert (destination / "keep").read_text() == "retained"
    assert (destination / ".git").is_file()
    assert not agent.calls
    assert store.load_state(contract.run_id).lifecycle.value == "CREATED"
    assert not (directory / ".execution").exists()


def test_unreadable_layout_never_falls_back_to_legacy(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    store, repo, contract = capture(tmp_path, frozen_contract)
    marker = store.directory(contract.run_id) / "workspace-layout.json"
    original = Path.stat
    original_lstat = Path.lstat

    def denied(self: Path, *, follow_symlinks: bool = True) -> stat_result:
        if self == marker:
            raise PermissionError("layout access denied")
        return original(self, follow_symlinks=follow_symlinks)

    def denied_lstat(self: Path) -> stat_result:
        if self == marker:
            raise PermissionError("layout access denied")
        return original_lstat(self)

    monkeypatch.setattr(Path, "stat", denied)
    monkeypatch.setattr(Path, "lstat", denied_lstat)
    agent = FakeAgent("clarify")
    with pytest.raises(ValueError, match="layout access denied"):
        execute_run(store=store, run_id=contract.run_id, repository=repo, agent=agent)
    assert not agent.calls
    assert store.load_state(contract.run_id).lifecycle.value == "CREATED"
