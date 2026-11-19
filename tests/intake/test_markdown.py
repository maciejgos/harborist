"""Real filesystem capture stays independent of subsequent source changes."""

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from harborist.domain import Run
from harborist.intake import MarkdownIntakeError, read_markdown_intent


@pytest.mark.parametrize(
    "content",
    [
        "---\ntitle: Café\n---\n\nFix the issue.\n".encode(),
        b"\xef\xbb\xbf# Request\r\n\r\nKeep exact bytes.\r\n",
        b"",
    ],
)
def test_file_capture_preserves_exact_content(tmp_path: Path, content: bytes) -> None:
    source = tmp_path / "request.txt"
    source.write_bytes(content)
    run = Run.create()
    before_run = run.model_dump_json()
    snapshot = read_markdown_intent(run_id=run.run_id, path=source)
    assert snapshot.markdown.encode("utf-8") == content
    assert snapshot.source_ref == f"file:{source.resolve()}"
    assert snapshot.run_id == run.run_id
    assert snapshot.artifact.size_bytes == len(content)
    assert source.read_bytes() == content
    assert list(tmp_path.iterdir()) == [source]
    assert run.model_dump_json() == before_run


def test_source_edits_and_deletion_do_not_mutate_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"Original request")
    snapshot = read_markdown_intent(run_id=uuid4(), path=source)
    before = snapshot.model_dump_json()
    source.write_bytes(b"Changed request")
    assert snapshot.markdown == "Original request"
    assert snapshot.model_dump_json() == before
    source.unlink()
    assert snapshot.markdown == "Original request"
    assert snapshot.model_dump_json() == before


def test_relative_path_resolves_against_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"Fix it")
    monkeypatch.chdir(tmp_path)
    snapshot = read_markdown_intent(run_id=uuid4(), path=Path("issue.md"))
    assert snapshot.source_ref == f"file:{source.resolve()}"


def test_symlink_uses_resolved_source_path(tmp_path: Path) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"Fix it")
    link = tmp_path / "linked.md"
    link.symlink_to(source)
    snapshot = read_markdown_intent(run_id=uuid4(), path=link)
    assert snapshot.source_ref == f"file:{source.resolve()}"
    assert snapshot.markdown == "Fix it"


@pytest.mark.parametrize(
    "input_kind,cause",
    [
        ("missing", FileNotFoundError),
        ("directory", IsADirectoryError),
        ("invalid-utf8", UnicodeDecodeError),
    ],
)
def test_input_failures_preserve_cause(
    tmp_path: Path, input_kind: str, cause: type[Exception]
) -> None:
    source = tmp_path / "issue.md"
    if input_kind == "directory":
        source.mkdir()
    elif input_kind == "invalid-utf8":
        source.write_bytes(b"\xff")
    with pytest.raises(MarkdownIntakeError) as caught:
        read_markdown_intent(run_id=uuid4(), path=source)
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value.__cause__, cause)
    assert str(source) in str(caught.value)


def test_permission_failure_is_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"Fix it")
    error = PermissionError("Permission denied")

    def deny_read(path: Path) -> bytes:
        raise error

    monkeypatch.setattr(Path, "read_bytes", deny_read)
    with pytest.raises(MarkdownIntakeError) as caught:
        read_markdown_intent(run_id=uuid4(), path=source)
    assert caught.value.__cause__ is error


def test_invalid_run_id_remains_a_model_error(tmp_path: Path) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"Fix it")
    with pytest.raises(ValidationError):
        read_markdown_intent(run_id=cast(UUID, "invalid"), path=source)


def test_capture_reads_source_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"Fix it")
    read_bytes = Path.read_bytes
    reads: list[Path] = []

    def count_read(path: Path) -> bytes:
        reads.append(path)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", count_read)
    snapshot = read_markdown_intent(run_id=uuid4(), path=source)
    assert snapshot.markdown == "Fix it"
    assert snapshot.artifact.size_bytes == 6
    assert reads == [source.resolve()]
