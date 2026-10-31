from pathlib import Path
from uuid import uuid4

import pytest

from shipyard.control.queue import QueueStore, Submission
from shipyard.control.read_model import read_record
from shipyard.control.service import ControlService
from shipyard.domain import RunContract
from shipyard.persistence import FileRunStore
from tests.application.test_run_execution import FakeAgent, capture


def test_read_model_distinguishes_delivery_run_and_missing_package(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    queue = QueueStore(tmp_path / "control")
    record = queue.submit(
        Submission(
            run_id=contract.run_id,
            repository=repo.checkout_root(),
            runs_root=store.directory(contract.run_id).parent,
        )
    )
    view = read_record(record).model_dump(mode="json")
    assert view["state"] == "QUEUED"
    assert view["run"]["lifecycle"] == "CREATED"
    assert not view["package_available"]
    service = ControlService(queue, agent=FakeAgent(), history_root=tmp_path / "runs")
    assert service.worker.execute_next()
    view = service.dispatch("GET", f"/runs/{contract.run_id}", b"")
    assert view["state"] == "FINISHED"
    assert view["package_available"]
    run = view["run"]
    assert isinstance(run, dict)
    assert run["outcome"] == "VERIFIED"
    assert view["attempt_id"] is not None
    assert service.dispatch("GET", "/runs", b"")["runs"] == [view]


def test_invalid_lifecycle_is_explicitly_unavailable(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store = FileRunStore(root=tmp_path / "runs")
    store.save(frozen_contract)
    queue = QueueStore(tmp_path / "control")
    record = queue.submit(
        Submission(
            run_id=frozen_contract.run_id,
            repository=tmp_path,
            runs_root=tmp_path / "runs",
        )
    )
    (store.directory(frozen_contract.run_id) / "run.json").write_text("{}")
    view = read_record(record).model_dump(mode="json")
    assert view["run"] is None
    assert view["run_error"]
    assert not view["package_available"]


def test_unknown_and_traversal_routes_fail(tmp_path: Path) -> None:
    service = ControlService(
        QueueStore(tmp_path / "control"),
        agent=FakeAgent(),
        history_root=tmp_path / "runs",
    )
    for path in (f"/runs/{uuid4()}", "/runs/../../secret", "/artifacts/etc/passwd"):
        with pytest.raises(ValueError):
            service.dispatch("GET", path, b"")
