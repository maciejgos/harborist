from pathlib import Path

import pytest

from shipyard.control.queue import DeliveryState, QueueStore, Submission
from shipyard.domain import RunContract
from shipyard.persistence import FileRunStore


def submission(tmp_path: Path, contract: RunContract) -> Submission:
    root = tmp_path / "runs"
    FileRunStore(root=root).save(contract)
    return Submission(run_id=contract.run_id, repository=tmp_path, runs_root=root)


def test_idempotent_submission_and_exclusive_claim(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    request = submission(tmp_path, frozen_contract)
    store = QueueStore(tmp_path / "control")
    record = store.submit(request)
    assert QueueStore(store.root).submit(request) == record
    assert store.claim().submission == request  # type: ignore[union-attr]
    assert QueueStore(store.root).claim() is None
    assert store.get(request.run_id).state == DeliveryState.RUNNING
    with pytest.raises(ValueError, match="Conflicting"):
        store.submit(
            Submission.model_validate(
                {**request.model_dump(), "workspace": tmp_path / "other"}
            )
        )


def test_restart_marks_claim_interrupted_without_requeue(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    request = submission(tmp_path, frozen_contract)
    store = QueueStore(tmp_path / "control")
    store.submit(request)
    store.claim()
    QueueStore(store.root).interrupt_claims()
    assert store.get(request.run_id).state == DeliveryState.INTERRUPTED
    assert store.claim() is None
    assert (
        FileRunStore(root=request.runs_root).load_state(request.run_id).lifecycle
        == "CREATED"
    )


def test_corrupt_queue_fails_closed(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    request = submission(tmp_path, frozen_contract)
    store = QueueStore(tmp_path / "control")
    store.submit(request)
    (store.root / "queue" / f"{request.run_id}.json").write_text("{}")
    with pytest.raises(ValueError):
        store.claim()
