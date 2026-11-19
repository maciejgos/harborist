from pathlib import Path

from harborist.control.queue import DeliveryState, QueueStore, Submission
from harborist.control.worker import Worker
from harborist.domain import RunContract
from harborist.domain.continuation import ContinuationRequest
from tests.application.test_run_execution import FakeAgent, capture


def test_service_serial_rework_and_idempotent_old_delivery(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    root = store.directory(contract.run_id).parent.resolve()
    queue = QueueStore(tmp_path / "control")
    initial = Submission(
        run_id=contract.run_id, repository=repo.checkout_root(), runs_root=root
    )
    queue.submit(initial)
    assert Worker(queue, agent=FakeAgent("changes")).execute_next()
    previous = store.load_state(contract.run_id)
    from harborist.domain.attempt import Attempt

    attempt = Attempt.model_validate_json(
        (store.directory(contract.run_id) / "attempt.json").read_bytes()
    )
    submission = Submission(
        run_id=contract.run_id,
        repository=repo.checkout_root(),
        runs_root=root,
        continuation=ContinuationRequest(
            action="rework",
            expected_attempt_id=attempt.attempt_id,
            feedback="Fix AC-001",
        ),
    )
    accepted = queue.submit(submission)
    assert accepted.state == DeliveryState.QUEUED
    assert queue.submit(submission) == accepted
    assert store.selected_number(contract.run_id) == 0
    assert Worker(queue, agent=FakeAgent()).execute_next()
    assert store.load_state(contract.run_id).outcome == "VERIFIED"
    assert previous.outcome == "CHANGES_REQUIRED"
    latest = queue.get(contract.run_id)
    assert latest.state == DeliveryState.FINISHED
    assert queue.submit(initial).submission == initial
    assert queue.get(contract.run_id) == latest
    assert not Worker(queue, agent=FakeAgent()).execute_next()


def test_latest_projection_uses_current_attempt_and_reused_spec(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from harborist.application.execution import execute_run
    from harborist.control.read_model import read_saved
    from harborist.persistence.continuation import prepare_continuation

    store, repo, contract = capture(tmp_path, frozen_contract)
    root = store.directory(contract.run_id).parent
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=FakeAgent("changes"),
    )
    assert first.attempt is not None
    selected, _ = prepare_continuation(
        store=store,
        run_id=contract.run_id,
        request=ContinuationRequest(
            action="rework", expected_attempt_id=first.attempt.attempt_id
        ),
    )
    result = execute_run(
        store=selected, run_id=contract.run_id, repository=repo, agent=FakeAgent()
    )
    view = read_saved(root, contract.run_id)
    assert view.run == result.run
    assert result.attempt is not None and view.attempt_id == result.attempt.attempt_id
    assert view.attempt_number == 1
    assert view.stages["design"].reason == "FROZEN_SPEC_REUSED"
    assert view.stage_errors == {}
    assert view.artifacts["report.md"] == str(
        selected.directory(contract.run_id) / "report.md"
    )
