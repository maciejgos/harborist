"""Acceptance tests for storage-independent artifact identity and provenance."""

import json
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from harborist.domain import (
    ArtifactKind,
    ArtifactReference,
    ArtifactSha256,
    ArtifactStage,
)

RUN_ID = uuid4()
ATTEMPT_ID = uuid4()
DIGEST = "0123456789abcdef" * 4


def metadata() -> dict[str, object]:
    return {
        "artifact_id": str(uuid4()),
        "run_id": str(RUN_ID),
        "kind": "intent",
        "produced_by": "intake",
        "sha256": DIGEST,
        "size_bytes": 0,
    }


def create(content: bytes, *, attempt_id: UUID | None = None) -> ArtifactReference:
    return ArtifactReference.create(
        run_id=RUN_ID,
        kind=ArtifactKind.INTENT,
        produced_by=ArtifactStage.INTAKE,
        content=content,
        attempt_id=attempt_id,
    )


@pytest.mark.parametrize(
    "content,digest,size",
    [
        (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", 0),
        (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", 3),
        (
            "é".encode(),
            "4a99557e4033c3539de2eb65472017cad5f9557f7a0625a09f1c3f6e2ba69c4c",
            2,
        ),
    ],
)
def test_known_content_vectors(content: bytes, digest: str, size: int) -> None:
    reference = create(content)
    assert reference.sha256 == digest
    assert reference.size_bytes == size
    assert reference.artifact_id.version == 4
    assert reference.run_id == RUN_ID
    assert reference.attempt_id is None
    assert reference.kind == ArtifactKind.INTENT
    assert reference.produced_by == ArtifactStage.INTAKE


def test_independent_records_can_share_content_identity() -> None:
    first, second = create(b"same"), create(b"same")
    attempt_owned = create(b"same", attempt_id=ATTEMPT_ID)
    other_run = ArtifactReference.create(
        run_id=uuid4(),
        kind=ArtifactKind.PLAN,
        produced_by=ArtifactStage.BUILD,
        content=b"same",
        attempt_id=uuid4(),
    )
    records = (first, second, attempt_owned, other_run)
    assert len({record.artifact_id for record in records}) == 4
    assert len({record.sha256 for record in records}) == 1
    assert {record.size_bytes for record in records} == {4}
    assert attempt_owned.attempt_id == ATTEMPT_ID
    assert other_run.run_id != first.run_id
    assert other_run.attempt_id != attempt_owned.attempt_id


def test_exact_bytes_are_not_normalized() -> None:
    assert create(b"change").sha256 != create(b"changed").sha256
    assert create(b"line\n").sha256 != create(b"line\r\n").sha256
    assert create(b"line\n").size_bytes == 5
    assert create(b"line\r\n").size_bytes == 6


@pytest.mark.parametrize(
    "content", ["abc", "", None, 1, True, bytearray(b"abc"), memoryview(b"abc"), [], {}]
)
def test_factory_rejects_non_bytes(content: object) -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        create(cast(bytes, content))


@pytest.mark.parametrize("kind", ArtifactKind)
def test_artifact_kinds(kind: ArtifactKind) -> None:
    reference = ArtifactReference.create(
        run_id=RUN_ID, kind=kind, produced_by=ArtifactStage.INTAKE, content=b""
    )
    assert reference.kind == kind
    assert reference.model_dump(mode="json")["kind"] == kind.value
    assert kind.name == kind.value.upper()


@pytest.mark.parametrize("stage", ArtifactStage)
def test_artifact_origins_without_kind_pairing_rules(stage: ArtifactStage) -> None:
    reference = ArtifactReference.create(
        run_id=RUN_ID, kind=ArtifactKind.INTENT, produced_by=stage, content=b""
    )
    assert reference.produced_by == stage
    assert reference.model_dump(mode="json")["produced_by"] == stage.value
    assert stage.name == stage.value.upper()


@pytest.mark.parametrize("attempt_id", [None, ATTEMPT_ID])
def test_direct_construction_and_json_round_trip(attempt_id: UUID | None) -> None:
    artifact_id = uuid4()
    reference = ArtifactReference(
        artifact_id=artifact_id,
        run_id=RUN_ID,
        attempt_id=attempt_id,
        kind=ArtifactKind.SPEC,
        produced_by=ArtifactStage.DESIGN,
        sha256=DIGEST,
        size_bytes=12,
    )
    assert reference.artifact_id == artifact_id
    assert reference.attempt_id == attempt_id
    assert (
        ArtifactReference.model_validate_json(reference.model_dump_json()) == reference
    )
    assert ArtifactReference.model_validate(metadata()).attempt_id is None


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 40,
        "a" * 63,
        "a" * 65,
        DIGEST.upper(),
        "g" * 64,
        " " + DIGEST,
        DIGEST + " ",
        DIGEST + "\n",
        "\t" + DIGEST,
        None,
        1,
        True,
    ],
)
def test_invalid_digests(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ArtifactSha256).validate_python(value)


def test_digest_rejects_bytes() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate({**metadata(), "sha256": b"a" * 64})


def test_reference_json_applies_digest_validation() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate_json(
            json.dumps({**metadata(), "sha256": "main"})
        )


@pytest.mark.parametrize("value", [-1, True, False, 0.0, 1.5, "0", None])
def test_size_is_a_strict_nonnegative_integer(value: object) -> None:
    data = {**metadata(), "size_bytes": value}
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate(data)


def test_required_fields() -> None:
    payload = metadata()
    for field in payload:
        data = {key: value for key, value in payload.items() if key != field}
        with pytest.raises(ValidationError, match="Field required"):
            ArtifactReference.model_validate(data)


@pytest.mark.parametrize("field", ["artifact_id", "run_id", "attempt_id"])
def test_invalid_identities(field: str) -> None:
    data = {**metadata(), field: "invalid"}
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate(data)


@pytest.mark.parametrize("field", ["artifact_id", "run_id"])
def test_required_identities_reject_null(field: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate({**metadata(), field: None})


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "unknown"),
        ("kind", "INTENT"),
        ("kind", None),
        ("produced_by", "unknown"),
        ("produced_by", "INTAKE"),
        ("produced_by", None),
    ],
)
def test_invalid_enums(field: str, value: object) -> None:
    data = {**metadata(), field: value}
    with pytest.raises(ValidationError):
        ArtifactReference.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "invalid"),
        ("attempt_id", "invalid"),
        ("kind", "unknown"),
        ("produced_by", "unknown"),
    ],
)
def test_factory_validates_metadata(field: str, value: object) -> None:
    data: dict[str, object] = {
        "run_id": RUN_ID,
        "attempt_id": None,
        "kind": ArtifactKind.INTENT,
        "produced_by": ArtifactStage.INTAKE,
        field: value,
    }
    with pytest.raises(ValidationError):
        ArtifactReference.create(
            run_id=cast(UUID, data["run_id"]),
            attempt_id=cast(UUID | None, data["attempt_id"]),
            kind=cast(ArtifactKind, data["kind"]),
            produced_by=cast(ArtifactStage, data["produced_by"]),
            content=b"content",
        )


def test_every_field_is_frozen() -> None:
    reference = create(b"abc", attempt_id=ATTEMPT_ID)
    before = reference.model_dump_json()
    for field in ArtifactReference.model_fields:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(reference, field, getattr(reference, field))
        with pytest.raises(ValidationError, match="frozen"):
            delattr(reference, field)
    assert reference.model_dump_json() == before


@pytest.mark.parametrize("field", ["content", "path"])
def test_unknown_fields_are_forbidden(field: str) -> None:
    data = {**metadata(), field: "unused"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ArtifactReference.model_validate_json(json.dumps(data))


def test_content_is_not_retained() -> None:
    reference = create(b"private source content")
    assert set(reference.model_dump()) == {
        "artifact_id",
        "run_id",
        "attempt_id",
        "kind",
        "produced_by",
        "sha256",
        "size_bytes",
    }
    assert "private source content" not in reference.model_dump_json()
    assert not hasattr(reference, "content")
