"""Complete captures are create-only and cross-validated on load."""

import json
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pytest

from shipyard.domain import Run, RunContract
from shipyard.persistence import (
    FileRunStore,
    RunAlreadyExistsError,
    RunPersistenceError,
)


def test_round_trip_and_exclusive_creation(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store = FileRunStore(root=tmp_path)
    store.save(frozen_contract)
    assert store.load(frozen_contract.run_id) == frozen_contract
    directory = tmp_path / str(frozen_contract.run_id)
    assert (
        directory / "intent.md"
    ).read_bytes() == frozen_contract.intent.markdown.encode()
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    with pytest.raises(RunAlreadyExistsError):
        store.save(frozen_contract)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize(
    "corruption", ["contract", "intent", "metadata", "run", "owner", "disagreement"]
)
def test_load_rejects_invalid_and_disagreeing_records(
    tmp_path: Path, frozen_contract: RunContract, corruption: str
) -> None:
    store = FileRunStore(root=tmp_path)
    store.save(frozen_contract)
    directory = tmp_path / str(frozen_contract.run_id)
    if corruption == "owner":
        (directory / "run.json").write_text(Run(run_id=uuid4()).model_dump_json())
    elif corruption == "disagreement":
        path = directory / "intent.json"
        payload = json.loads(path.read_bytes())
        payload["source_ref"] = "github:other/source#1"
        path.write_text(json.dumps(payload))
    else:
        name = {
            "contract": "contract.json",
            "intent": "intent.md",
            "metadata": "intent.json",
            "run": "run.json",
        }[corruption]
        (directory / name).write_text("corrupt")
    with pytest.raises(RunPersistenceError) as caught:
        store.load(frozen_contract.run_id)
    assert caught.value.__cause__ is not None


def test_failed_write_retains_evidence_and_blocks_retry(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileRunStore(root=tmp_path)
    original = Path.open

    def fail_contract(path: Path, mode: str = "r") -> BinaryIO:
        if path.name == "contract.json":
            raise OSError("Disk full")
        assert mode == "xb"
        return original(path, "xb")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_contract)
        with pytest.raises(RunPersistenceError) as caught:
            store.save(frozen_contract)
        assert isinstance(caught.value.__cause__, OSError)
    directory = tmp_path / str(frozen_contract.run_id)
    assert (directory / "intent.md").exists()
    assert not (directory / "contract.json").exists()
    with pytest.raises(RunPersistenceError):
        store.load(frozen_contract.run_id)
    with pytest.raises(RunAlreadyExistsError):
        store.save(frozen_contract)


def test_root_io_error_is_wrapped(tmp_path: Path, frozen_contract: RunContract) -> None:
    root = tmp_path / "file"
    root.write_text("Not a directory")
    with pytest.raises(RunPersistenceError) as caught:
        FileRunStore(root=root).save(frozen_contract)
    assert isinstance(caught.value.__cause__, OSError)
