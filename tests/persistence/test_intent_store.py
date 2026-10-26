"""Create-only intent persistence, independent of the original source file."""

import json
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from shipyard.domain import IntentSnapshot
from shipyard.intake import read_markdown_intent
from shipyard.persistence import (
    FileIntentStore,
    IntentAlreadyExistsError,
    IntentPersistenceError,
)


def test_constructor_performs_no_io(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    FileIntentStore(root=root)
    assert not root.exists()


@pytest.mark.parametrize(
    "content",
    [
        b"\xef\xbb\xbf---\r\ntitle: Caf\xc3\xa9\r\n---\r\n\r\nFix it.\r\n",
        b"",
    ],
)
def test_save_load_preserves_exact_intent_after_source_deletion(
    tmp_path: Path, content: bytes
) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(content)
    snapshot = read_markdown_intent(run_id=uuid4(), path=source)
    root = tmp_path / "runs"
    store = FileIntentStore(root=root)
    assert store.save(snapshot) is None
    directory = root / str(snapshot.run_id)
    assert (directory / "intent.md").read_bytes() == content
    assert json.loads((directory / "intent.json").read_bytes()) == {
        "source_ref": snapshot.source_ref,
        "artifact": snapshot.artifact.model_dump(mode="json"),
    }
    assert {path.name for path in directory.iterdir()} == {"intent.md", "intent.json"}
    source.write_bytes(b"Revised source")
    assert store.load(snapshot.run_id) == snapshot
    source.unlink()
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    loaded = FileIntentStore(root=root).load(snapshot.run_id)
    assert loaded == snapshot
    assert loaded.artifact.artifact_id == snapshot.artifact.artifact_id
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


def make_snapshot() -> IntentSnapshot:
    return IntentSnapshot.create(
        run_id=uuid4(), source_ref="file:/deleted.md", markdown="Original request"
    )


def test_save_preserves_unrelated_files(tmp_path: Path) -> None:
    snapshot = make_snapshot()
    directory = tmp_path / str(snapshot.run_id)
    directory.mkdir()
    unrelated = directory / "run.json"
    unrelated.write_bytes(b"Existing state")
    store = FileIntentStore(root=tmp_path)
    store.save(snapshot)
    assert unrelated.read_bytes() == b"Existing state"
    assert store.load(snapshot.run_id) == snapshot


@pytest.mark.parametrize("changed", [False, True])
def test_repeat_save_rejects_identical_or_changed_snapshots(
    tmp_path: Path, changed: bool
) -> None:
    snapshot = make_snapshot()
    store = FileIntentStore(root=tmp_path)
    store.save(snapshot)
    directory = tmp_path / str(snapshot.run_id)
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    if changed:
        snapshot = IntentSnapshot.create(
            run_id=snapshot.run_id,
            source_ref=snapshot.source_ref,
            markdown="Different request",
        )
    with pytest.raises(IntentAlreadyExistsError):
        store.save(snapshot)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize("existing", ["intent.md", "intent.json"])
def test_orphan_file_blocks_save_without_creating_other_files(
    tmp_path: Path, existing: str
) -> None:
    snapshot = make_snapshot()
    directory = tmp_path / str(snapshot.run_id)
    directory.mkdir()
    reserved = directory / existing
    reserved.write_bytes(b"Keep this partial evidence")
    store = FileIntentStore(root=tmp_path)
    with pytest.raises(IntentAlreadyExistsError):
        store.save(snapshot)
    assert list(directory.iterdir()) == [reserved]
    assert reserved.read_bytes() == b"Keep this partial evidence"
    with pytest.raises(IntentPersistenceError):
        store.load(snapshot.run_id)


def test_exclusive_create_protects_against_conflict_after_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = make_snapshot()
    directory = tmp_path / str(snapshot.run_id)

    def intervening_writer(path: Path) -> bool:
        if path.name == "intent.json":
            (directory / "intent.md").write_bytes(b"Another writer's evidence")
        return False

    monkeypatch.setattr("shipyard.persistence.intent.lexists", intervening_writer)
    with pytest.raises(IntentAlreadyExistsError) as caught:
        FileIntentStore(root=tmp_path).save(snapshot)
    assert isinstance(caught.value.__cause__, FileExistsError)
    assert (directory / "intent.md").read_bytes() == b"Another writer's evidence"
    assert not (directory / "intent.json").exists()


def test_existing_broken_symlink_blocks_save(tmp_path: Path) -> None:
    snapshot = make_snapshot()
    directory = tmp_path / str(snapshot.run_id)
    directory.mkdir()
    reserved = directory / "intent.json"
    reserved.symlink_to(directory / "missing-target")
    with pytest.raises(IntentAlreadyExistsError):
        FileIntentStore(root=tmp_path).save(snapshot)
    assert reserved.is_symlink()
    assert not (directory / "intent.md").exists()


def test_metadata_write_failure_leaves_detectable_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = make_snapshot()
    directory = tmp_path / str(snapshot.run_id)
    store = FileIntentStore(root=tmp_path)
    error = OSError("Simulated disk full")
    real_open = Path.open

    def fail_metadata_open(
        path: Path, mode: str = "r", buffering: int = -1
    ) -> BinaryIO:
        if path.name == "intent.json" and mode == "xb":
            # The content file must already have been closed before metadata creation.
            assert (directory / "intent.md").read_bytes() == snapshot.markdown.encode()
            raise error
        return cast(BinaryIO, real_open(path, mode, buffering=buffering))

    monkeypatch.setattr(Path, "open", fail_metadata_open)
    with pytest.raises(IntentPersistenceError) as caught:
        store.save(snapshot)
    assert caught.value.__cause__ is error
    assert "save" in str(caught.value)
    assert str(directory / "intent.json") in str(caught.value)
    assert (directory / "intent.md").read_bytes() == snapshot.markdown.encode()
    assert not (directory / "intent.json").exists()
    with pytest.raises(IntentAlreadyExistsError):
        store.save(snapshot)
    with pytest.raises(IntentPersistenceError) as missing:
        store.load(snapshot.run_id)
    assert isinstance(missing.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize(
    "corruption,cause",
    [
        ("invalid-json", ValidationError),
        ("duplicated-markdown", ValidationError),
        ("missing-source-ref", ValidationError),
        ("wrong-kind", ValidationError),
        ("modified-text", ValidationError),
        ("truncated-text", ValidationError),
        ("invalid-utf8", UnicodeDecodeError),
        ("wrong-owner", ValueError),
    ],
)
def test_corrupt_intent_is_rejected_without_repair(
    tmp_path: Path, corruption: str, cause: type[Exception]
) -> None:
    snapshot = make_snapshot()
    store = FileIntentStore(root=tmp_path)
    store.save(snapshot)
    directory = tmp_path / str(snapshot.run_id)
    metadata_path = directory / "intent.json"
    content_path = directory / "intent.md"
    metadata = json.loads(metadata_path.read_bytes())
    match corruption:
        case "invalid-json":
            metadata_path.write_bytes(b"{Original request")
        case "duplicated-markdown":
            metadata["markdown"] = snapshot.markdown
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        case "missing-source-ref":
            del metadata["source_ref"]
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        case "wrong-kind":
            metadata["artifact"]["kind"] = "spec"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        case "modified-text":
            content_path.write_bytes(b"Modified request")
            assert content_path.stat().st_size == snapshot.artifact.size_bytes
        case "truncated-text":
            content_path.write_bytes(b"Original")
        case "invalid-utf8":
            content_path.write_bytes(b"\xff")
        case "wrong-owner":
            metadata["artifact"]["run_id"] = str(uuid4())
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        case _:
            raise AssertionError(f"Unknown test corruption: {corruption}")
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    with pytest.raises(IntentPersistenceError) as caught:
        store.load(snapshot.run_id)
    assert isinstance(caught.value.__cause__, cause)
    assert "load" in str(caught.value)
    assert str(directory) in str(caught.value)
    assert snapshot.markdown not in str(caught.value)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize("missing", ["intent.md", "intent.json"])
def test_missing_persisted_file_is_rejected(tmp_path: Path, missing: str) -> None:
    snapshot = make_snapshot()
    store = FileIntentStore(root=tmp_path)
    store.save(snapshot)
    (tmp_path / str(snapshot.run_id) / missing).unlink()
    with pytest.raises(IntentPersistenceError) as caught:
        store.load(snapshot.run_id)
    assert isinstance(caught.value.__cause__, FileNotFoundError)


def test_save_revalidates_snapshot_before_creating_directories(tmp_path: Path) -> None:
    snapshot = make_snapshot().model_copy(update={"markdown": "Tampered content"})
    root = tmp_path / "runs"
    with pytest.raises(ValidationError):
        FileIntentStore(root=root).save(snapshot)
    assert not root.exists()


def test_load_validates_run_id_before_constructing_path(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    with pytest.raises(ValidationError):
        FileIntentStore(root=root).load(cast(UUID, "../invalid"))
    assert not root.exists()


def test_directory_creation_failure_is_a_chained_io_error(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    root.write_bytes(b"Existing file blocks the directory")
    with pytest.raises(IntentPersistenceError) as caught:
        FileIntentStore(root=root).save(make_snapshot())
    assert not isinstance(caught.value, IntentAlreadyExistsError)
    assert isinstance(caught.value.__cause__, OSError)
    assert root.read_bytes() == b"Existing file blocks the directory"
