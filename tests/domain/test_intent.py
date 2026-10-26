"""Intent content and provenance are an immutable, internally consistent capture."""

import hashlib
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shipyard.domain import ArtifactKind, ArtifactStage, IntentSnapshot


def test_snapshot_factory_preserves_content_and_ownership() -> None:
    run_id = uuid4()
    markdown = "---\ntitle: Café\n---\n\nFix the issue.\n"
    first = IntentSnapshot.create(
        run_id=run_id, source_ref="file:/issue.md", markdown=markdown
    )
    second = IntentSnapshot.create(
        run_id=run_id, source_ref="file:/issue.md", markdown=markdown
    )
    assert first.markdown == markdown
    assert first.source_ref == "file:/issue.md"
    assert first.run_id == run_id
    assert first.artifact.kind == ArtifactKind.INTENT
    assert first.artifact.produced_by == ArtifactStage.INTAKE
    assert first.artifact.attempt_id is None
    assert first.artifact.sha256 == hashlib.sha256(markdown.encode()).hexdigest()
    assert first.artifact.size_bytes == len(markdown.encode())
    assert first.artifact.sha256 == second.artifact.sha256
    assert first.artifact.artifact_id != second.artifact.artifact_id
    assert IntentSnapshot.model_validate_json(first.model_dump_json()) == first
    assert "run_id" not in first.model_dump()


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "spec"),
        ("produced_by", "design"),
        ("attempt_id", str(uuid4())),
        ("sha256", "0" * 64),
        ("size_bytes", 100),
    ],
)
def test_snapshot_rejects_inconsistent_artifact(field: str, value: object) -> None:
    snapshot = IntentSnapshot.create(
        run_id=uuid4(), source_ref="file:/issue.md", markdown="Fix it"
    )
    payload = {
        **snapshot.model_dump(mode="json"),
        "artifact": {**snapshot.artifact.model_dump(mode="json"), field: value},
    }
    with pytest.raises(ValidationError):
        IntentSnapshot.model_validate(payload)


def test_json_cannot_change_content_without_updating_artifact() -> None:
    snapshot = IntentSnapshot.create(
        run_id=uuid4(), source_ref="file:/issue.md", markdown="Fix it"
    )
    payload = snapshot.model_dump_json().replace("Fix it", "Different content")
    with pytest.raises(ValidationError):
        IntentSnapshot.model_validate_json(payload)


def test_snapshot_fields_and_ownership_are_frozen() -> None:
    snapshot = IntentSnapshot.create(
        run_id=uuid4(), source_ref="file:/issue.md", markdown="Fix it"
    )
    before = snapshot.model_dump_json()
    for field in (*IntentSnapshot.model_fields, "run_id"):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(snapshot, field, getattr(snapshot, field))
        with pytest.raises(ValidationError, match="frozen"):
            delattr(snapshot, field)
    assert snapshot.model_dump_json() == before


@pytest.mark.parametrize(
    "updates",
    [
        {"source_ref": ""},
        {"source_ref": 123},
        {"markdown": b"Fix it"},
        {"markdown": "\ud800"},
        {"unexpected": True},
    ],
)
def test_snapshot_rejects_invalid_fields(updates: dict[str, object]) -> None:
    snapshot = IntentSnapshot.create(
        run_id=uuid4(), source_ref="file:/issue.md", markdown="Fix it"
    )
    with pytest.raises(ValidationError):
        IntentSnapshot.model_validate({**snapshot.model_dump(), **updates})


def test_factory_validates_text_before_hashing() -> None:
    with pytest.raises(ValidationError):
        IntentSnapshot.create(
            run_id=uuid4(), source_ref="file:/issue.md", markdown=cast(str, b"Fix it")
        )
