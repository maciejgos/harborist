from pathlib import Path

import pytest

from shipyard.control.queue import DeliveryState, QueueStore, Submission
from shipyard.control.read_model import read_saved
from shipyard.control.worker import Worker
from shipyard.domain import RunContract
from shipyard.domain.attempt import Attempt
from shipyard.domain.continuation import ContinuationRequest
from tests.application.test_phase11_acceptance import CrashAtPlan
from tests.application.test_run_execution import FakeAgent, capture


def test_interrupted_claim_requires_explicit_recovery_delivery(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    root = store.directory(contract.run_id).parent
    queue = QueueStore(tmp_path / "control")
    initial = Submission(
        run_id=contract.run_id, repository=repo.checkout_root(), runs_root=root
    )
    queue.submit(initial)
    with pytest.raises(SystemExit):
        Worker(queue, agent=CrashAtPlan()).execute_next()
    queue.interrupt_claims()
    assert queue.get(contract.run_id).state == DeliveryState.INTERRUPTED
    assert not Worker(queue, agent=FakeAgent()).execute_next()
    previous = Attempt.model_validate_json(
        (store.directory(contract.run_id) / "attempt.json").read_bytes()
    )
    recovery = Submission(
        run_id=contract.run_id,
        repository=repo.checkout_root(),
        runs_root=root,
        continuation=ContinuationRequest(
            action="recover",
            expected_attempt_id=previous.attempt_id,
            additional_seconds=600,
        ),
    )
    queue.submit(recovery)
    assert Worker(queue, agent=FakeAgent()).execute_next()
    assert store.load_state(contract.run_id).outcome == "VERIFIED"
    assert queue.get(contract.run_id).state == DeliveryState.FINISHED
    assert queue.submit(initial).state == DeliveryState.INTERRUPTED


def test_broken_attempt_history_is_reported_without_hiding_other_runs(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    directory = store.directory(contract.run_id)
    (directory / "attempts" / "bad").mkdir(parents=True)
    view = read_saved(directory.parent, contract.run_id)
    assert view.run is None
    assert view.run_error is not None


def test_dangling_attempts_link_never_falls_back_to_verified_history(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from shipyard.application.execution import execute_run

    store, repo, contract = capture(tmp_path, frozen_contract)
    directory = store.directory(contract.run_id)
    execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=FakeAgent(),
    )
    (directory / "attempts").symlink_to(tmp_path / "missing-attempt-history")
    view = read_saved(directory.parent, contract.run_id)
    assert view.run is None
    assert view.run_error is not None
