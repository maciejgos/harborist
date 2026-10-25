"""Acceptance tests for Attempt and candidate revision identity."""

import json
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from shipyard.domain import Attempt, Candidate, GitCommitSha, Run

SHA1 = "0123456789abcdef" * 2 + "01234567"
SHA256 = "abcdef0123456789" * 4
ATTEMPT_ID = uuid4()
RUN_ID = uuid4()
RECORDS: list[tuple[type[BaseModel], dict[str, object]]] = [
    (
        Attempt,
        {"attempt_id": str(ATTEMPT_ID), "run_id": str(RUN_ID), "start_sha": SHA1},
    ),
    (Candidate, {"attempt_id": str(ATTEMPT_ID), "candidate_sha": SHA256}),
]
INVALID_HASHES: list[object] = [
    "",
    "a" * 7,
    "a" * 39,
    "a" * 41,
    "a" * 63,
    "a" * 65,
    "main",
    "refs/heads/main",
    "HEAD",
    SHA1.upper(),
    SHA256.upper(),
    "g" * 40,
    "é" * 64,
    " " + SHA1,
    SHA1 + " ",
    SHA1 + "\n",
    "\n" + SHA256,
    SHA256 + "\n",
    "\t" + SHA1,
    SHA256 + "\r\n",
    "a" * 20 + " " + "a" * 19,
    None,
    123,
    True,
    [],
    {},
]


def test_fresh_attempts_and_candidate_ownership() -> None:
    run = Run.create()
    first = Attempt.create(run.run_id, SHA1)
    second = Attempt.create(run.run_id, SHA1)
    assert first.attempt_id != second.attempt_id
    assert first.attempt_id.version == second.attempt_id.version == 4
    assert first.run_id == second.run_id == run.run_id
    assert first.start_sha == second.start_sha == SHA1

    before = first.model_dump_json()
    candidate = first.create_candidate(SHA256)
    assert candidate.attempt_id == first.attempt_id
    assert candidate.candidate_sha == SHA256
    assert first.model_dump_json() == before
    assert candidate == Candidate(attempt_id=first.attempt_id, candidate_sha=SHA256)
    assert candidate != second.create_candidate(SHA256)


@pytest.mark.parametrize("sha", [SHA1, SHA256])
def test_full_hashes_across_constructors_helpers_and_json(sha: str) -> None:
    attempt = Attempt(attempt_id=ATTEMPT_ID, run_id=RUN_ID, start_sha=sha)
    assert attempt.attempt_id == ATTEMPT_ID
    assert attempt.run_id == RUN_ID
    assert attempt.start_sha == sha
    assert Attempt.create(RUN_ID, sha).start_sha == sha
    candidate = Candidate(attempt_id=ATTEMPT_ID, candidate_sha=sha)
    assert attempt.create_candidate(sha) == candidate
    assert Candidate.model_validate_json(candidate.model_dump_json()) == candidate
    assert Attempt.model_validate_json(attempt.model_dump_json()) == attempt
    assert TypeAdapter(GitCommitSha).validate_python(sha) == sha


@pytest.mark.parametrize("value", INVALID_HASHES)
def test_invalid_hashes_across_constructors_helpers_and_json(value: object) -> None:
    # Casts deliberately exercise invalid runtime input through the typed APIs.
    invalid = cast(str, value)
    with pytest.raises(ValidationError):
        Attempt(attempt_id=ATTEMPT_ID, run_id=RUN_ID, start_sha=invalid)
    with pytest.raises(ValidationError):
        Candidate(attempt_id=ATTEMPT_ID, candidate_sha=invalid)
    with pytest.raises(ValidationError):
        Attempt.create(RUN_ID, invalid)
    with pytest.raises(ValidationError):
        Attempt.create(RUN_ID, SHA1).create_candidate(invalid)
    for model, payload in RECORDS:
        field = "start_sha" if model is Attempt else "candidate_sha"
        data = {**payload, field: value}
        with pytest.raises(ValidationError):
            model.model_validate(data)
        with pytest.raises(ValidationError):
            model.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("value", [b"a" * 40, b"a" * 64, bytearray(b"a" * 40)])
def test_hashes_reject_byte_strings(value: object) -> None:
    with pytest.raises(ValidationError):
        Attempt.create(RUN_ID, cast(str, value))
    with pytest.raises(ValidationError):
        Candidate(attempt_id=ATTEMPT_ID, candidate_sha=cast(str, value))


@pytest.mark.parametrize("model,payload", RECORDS)
def test_every_field_is_required_and_frozen(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    record = model.model_validate(payload)
    before = record.model_dump_json()
    for field, original_value in payload.items():
        incomplete = {key: value for key, value in payload.items() if key != field}
        with pytest.raises(ValidationError, match="Field required"):
            model.model_validate(incomplete)
        with pytest.raises(ValidationError, match="Field required"):
            model.model_validate_json(json.dumps(incomplete))
        with pytest.raises(ValidationError, match="frozen"):
            setattr(record, field, original_value)
        with pytest.raises(ValidationError, match="frozen"):
            delattr(record, field)
    assert record.model_dump_json() == before


@pytest.mark.parametrize("model,payload", RECORDS)
@pytest.mark.parametrize("value", ["not-a-uuid", "", None, 1])
def test_invalid_identities(
    model: type[BaseModel], payload: dict[str, object], value: object
) -> None:
    for field in payload:
        if field.endswith("_id"):
            data = {**payload, field: value}
            with pytest.raises(ValidationError):
                model.model_validate(data)
            with pytest.raises(ValidationError):
                model.model_validate_json(json.dumps(data))
    with pytest.raises(ValidationError):
        Attempt.create(cast(UUID, value), SHA1)


@pytest.mark.parametrize("model,payload", RECORDS)
@pytest.mark.parametrize("field", ["unexpected", "candidate_id", "verified"])
def test_unknown_fields_are_forbidden(
    model: type[BaseModel], payload: dict[str, object], field: str
) -> None:
    data = {**payload, field: "extra"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate(data)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("model", [Attempt, Candidate])
@pytest.mark.parametrize("payload", ["{", "[]", "null"])
def test_malformed_or_non_record_json(model: type[BaseModel], payload: str) -> None:
    with pytest.raises(ValidationError):
        model.model_validate_json(payload)


def test_records_do_not_enforce_repository_or_uniqueness_rules() -> None:
    attempt = Attempt.create(RUN_ID, SHA1)
    candidate = attempt.create_candidate(SHA1)
    assert candidate.candidate_sha == attempt.start_sha
    assert candidate == attempt.create_candidate(SHA1)
    assert attempt.create_candidate(SHA256).candidate_sha == SHA256
    # Standalone construction records ownership without looking up an Attempt.
    standalone = Candidate(attempt_id=uuid4(), candidate_sha=SHA1)
    assert standalone.attempt_id != attempt.attempt_id
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Candidate.model_validate({**standalone.model_dump(), "run_id": RUN_ID})
