from pathlib import Path

from shipyard.control.queue import DeliveryState, QueueStore, Submission
from shipyard.control.worker import Worker
from shipyard.domain import RunContract
from shipyard.persistence import FileRunStore
from tests.application.test_run_execution import FakeAgent, capture


def test_worker_uses_real_executor_and_preserves_verified_sha(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    run_store, repository, contract = capture(tmp_path, frozen_contract)
    queue = QueueStore(tmp_path / "control")
    queue.submit(
        Submission(
            run_id=contract.run_id,
            repository=repository.checkout_root(),
            runs_root=run_store.directory(contract.run_id).parent.resolve(),
        )
    )
    agent = FakeAgent()
    worker = Worker(queue, agent=agent)
    assert worker.execute_next()
    record = queue.get(contract.run_id)
    assert record.state == DeliveryState.FINISHED
    run = run_store.load_state(contract.run_id)
    assert run.outcome == "VERIFIED"
    assert run.verification is not None
    assert run.verification.candidate.candidate_sha
    assert len(agent.calls) == 4
    assert not worker.execute_next()
    assert record.progress is not None
    assert record.progress.stage == "package"
    assert record.progress.state == "completed"


def test_worker_records_preflight_failure_without_retry(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store = FileRunStore(root=tmp_path / "runs")
    store.save(frozen_contract)
    queue = QueueStore(tmp_path / "control")
    queue.submit(
        Submission(
            run_id=frozen_contract.run_id,
            repository=tmp_path,
            runs_root=tmp_path / "runs",
        )
    )
    worker = Worker(queue, agent=FakeAgent())
    assert worker.execute_next()
    record = queue.get(frozen_contract.run_id)
    assert record.state == DeliveryState.FAILED
    assert record.error
    assert not worker.execute_next()
