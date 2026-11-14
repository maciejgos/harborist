from pathlib import Path

import pytest

from shipyard.control.queue import QueueStore, Submission
from shipyard.control.service import ControlService
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture


def test_cancel_queued_run_prevents_claim(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    root = store.original_directory(contract.run_id).parent
    queue = QueueStore(tmp_path / "control")
    service = ControlService(queue, agent=FakeAgent(), history_root=root)
    submission = Submission(
        run_id=contract.run_id, repository=repo.checkout_root(), runs_root=root
    )
    queue.submit(submission)
    result = service.dispatch(
        "POST", f"/runs/{contract.run_id}/cancel", b'{"reason":"withdrawn"}'
    )
    assert result["reason"] == "withdrawn"
    assert queue.claim() is None
    assert store.load_state(contract.run_id).lifecycle == "CANCELLED"
    with pytest.raises(ValueError, match="terminal"):
        queue.submit(submission)


def test_supersede_active_run_stops_execution_and_queues_fresh_contract(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from shipyard.agents.base import AgentRequest, AgentResponse
    from shipyard.application.context import ExecutionContext
    from shipyard.application.intake import create_run
    from shipyard.control.queue import DeliveryState

    store, repo, contract = capture(tmp_path, frozen_contract)
    run_id = contract.run_id
    root = store.original_directory(run_id).parent
    source = tmp_path / "replacement.md"
    source.write_text("# Replacement\n\nImplement the updated request.")
    replacement = create_run(
        source=f"file:{source}",
        repository=repo,
        store=store,
        execution=contract.execution,
        ref=contract.base_sha,
    )
    ExecutionContext(
        version=1,
        run_id=replacement.run_id,
        repository=repo.checkout_root(),
        runs_root=root,
    ).save()
    queue = QueueStore(tmp_path / "control")

    class SupersedingAgent(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            result = service.dispatch(
                "POST",
                f"/runs/{run_id}/supersede",
                RetirementRequest(
                    reason="Updated request", replacement=replacement.run_id
                )
                .model_dump_json()
                .encode(),
            )
            assert result["replacement"] == str(replacement.run_id)
            return super().execute(request)

    from shipyard.persistence.retirement import RetirementRequest

    service = ControlService(queue, agent=SupersedingAgent(), history_root=root)
    queue.submit(
        Submission(run_id=run_id, repository=repo.checkout_root(), runs_root=root)
    )
    service.active = queue.claim()
    assert service.active is not None
    service.worker.execute(service.active)
    assert queue.get(run_id).state == DeliveryState.CANCELLED
    assert store.load_state(run_id).lifecycle == "CANCELLED"
    assert queue.get(replacement.run_id).state == DeliveryState.QUEUED
    replacement_state = store.load_state(replacement.run_id)
    assert replacement_state.lifecycle == "CREATED"
    assert replacement_state.verification is None


def test_cancel_completed_candidate_preserves_evidence_and_blocks_publication(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shipyard.application.execution import execute_run
    from shipyard.application.publication import publish_run

    store, repo, contract = capture(tmp_path, frozen_contract)
    run_id = contract.run_id
    root = store.original_directory(run_id).parent
    evidence = execute_run(
        store=store,
        run_id=run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent(),
    )
    assert evidence.candidate is not None
    evidence_path = store.directory(run_id) / "evidence.json"
    before = evidence_path.read_bytes()
    service = ControlService(
        QueueStore(tmp_path / "control"), agent=FakeAgent(), history_root=root
    )
    request = b'{"reason":"Withdraw unpublished change"}'
    cancelled = service.dispatch("POST", f"/runs/{run_id}/cancel", request)
    assert cancelled == service.dispatch("POST", f"/runs/{run_id}/cancel", request)
    assert evidence_path.read_bytes() == before
    assert store.load_state(run_id).verification == evidence.run.verification
    monkeypatch.chdir(repo.checkout_root())
    with pytest.raises(ValueError, match="terminal"):
        publish_run(
            run_id,
            approve=evidence.candidate.candidate_sha,
            destination="owner/repo",
            base="main",
            runs_dir=root,
        )
