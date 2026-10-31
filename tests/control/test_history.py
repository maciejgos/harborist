from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from shipyard.application.execution import execute_run
from shipyard.control.queue import QueueStore, Submission
from shipyard.control.service import ControlService
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture


def test_saved_foreground_run_is_listed_readable_and_never_queued(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    execute_run(store=store, run_id=contract.run_id, repository=repo, agent=FakeAgent())
    directory = store.directory(contract.run_id)
    before = {
        name: (directory / name).read_bytes()
        for name in ("run.json", "events.jsonl", "report.md", "evidence.json")
    }
    queue = QueueStore(tmp_path / "control")
    service = ControlService(queue, agent=FakeAgent(), history_root=directory.parent)
    listing = cast(
        list[dict[str, object]], service.dispatch("GET", "/runs", b"")["runs"]
    )
    assert isinstance(listing, list)
    assert len(listing) == 1
    detail = service.dispatch("GET", f"/runs/{contract.run_id}", b"")
    assert listing == [detail]
    assert detail["source"] == "saved"
    assert detail["state"] is None
    assert detail["package_available"]
    assert detail["stages"] == {}
    assert detail["candidate_sha"] is not None
    assert detail["submitted_at"] is None
    report = service.dispatch(
        "GET", f"/runs/{contract.run_id}/artifacts/report.md", b""
    )
    assert report["content"] == before["report.md"].decode()
    assert queue.list() == []
    assert before == {name: (directory / name).read_bytes() for name in before}


def test_service_metadata_wins_without_duplicate_history_entry(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    queue = QueueStore(tmp_path / "control")
    queue.submit(
        Submission(
            run_id=contract.run_id,
            repository=repo.checkout_root(),
            runs_root=store.directory(contract.run_id).parent,
        )
    )
    service = ControlService(
        queue, agent=FakeAgent(), history_root=store.directory(contract.run_id).parent
    )
    listing = cast(
        list[dict[str, object]], service.dispatch("GET", "/runs", b"")["runs"]
    )
    assert isinstance(listing, list) and len(listing) == 1
    assert listing[0]["source"] == "service"
    assert listing[0]["state"] == "QUEUED"


def test_bad_capture_does_not_hide_history_and_symlinks_are_ignored(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    root = store.directory(contract.run_id).parent
    bad_id = uuid4()
    (root / str(bad_id)).mkdir()
    (root / "notes.txt").write_text("not a Run")
    (root / str(uuid4())).symlink_to(
        store.directory(contract.run_id), target_is_directory=True
    )
    service = ControlService(
        QueueStore(tmp_path / "control"), agent=FakeAgent(), history_root=root
    )
    listing = cast(
        list[dict[str, object]], service.dispatch("GET", "/runs", b"")["runs"]
    )
    assert isinstance(listing, list) and len(listing) == 2
    bad = service.dispatch("GET", f"/runs/{bad_id}", b"")
    assert bad["run"] is None and bad["run_error"]
    assert service.dispatch("GET", f"/runs/{contract.run_id}", b"")["run"] is not None


def test_missing_history_root_and_conflicting_uuid_fail_safely(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    queue = QueueStore(tmp_path / "control")
    service = ControlService(
        queue, agent=FakeAgent(), history_root=tmp_path / "missing"
    )
    assert service.dispatch("GET", "/runs", b"")["runs"] == []
    store, repo, contract = capture(tmp_path, frozen_contract)
    queue.submit(
        Submission(
            run_id=contract.run_id,
            repository=repo.checkout_root(),
            runs_root=store.directory(contract.run_id).parent,
        )
    )
    other = tmp_path / "other-runs"
    (other / str(contract.run_id)).mkdir(parents=True)
    service = ControlService(queue, agent=FakeAgent(), history_root=other)
    with pytest.raises(ValueError, match="multiple Runs roots"):
        service.dispatch("GET", "/runs", b"")


def test_default_history_discovers_home_and_orders_saved_runs(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from shipyard.domain import IntentSnapshot
    from shipyard.persistence import FileRunStore

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    root = home / ".shipyard" / "runs"
    store = FileRunStore(root=root)
    store.save(frozen_contract)
    second_id = uuid4()
    second = RunContract.model_validate(
        {
            **frozen_contract.model_dump(),
            "run_id": second_id,
            "intent": IntentSnapshot.create(
                run_id=second_id, source_ref="file:/second.md", markdown="# Second"
            ),
        }
    )
    store.save(second)
    for run_id, timestamp in ((frozen_contract.run_id, 1000), (second_id, 2000)):
        os.utime(store.directory(run_id) / "contract.json", (timestamp, timestamp))
    service = ControlService(QueueStore(tmp_path / "control"), agent=FakeAgent())
    records = service.history.list()
    assert [view.submission.run_id for view in records] == [
        frozen_contract.run_id,
        second_id,
    ]
    assert all(view.source == "saved" and view.state is None for view in records)
