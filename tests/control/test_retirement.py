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
