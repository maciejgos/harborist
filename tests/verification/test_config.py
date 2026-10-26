"""Verification settings are declarations; parsing never executes checks."""

import pytest
from pydantic import ValidationError

from shipyard.domain import VerificationConfig, VerificationConfigSnapshot
from shipyard.verification import VerificationConfigError, parse_verification_config

SOURCE = b'version: 1\nchecks:\n  - id: tests\n    command: " pytest -q "\n  - id: lint\n    command: ruff check .\n'


def test_supported_config_preserves_check_order_and_command_text() -> None:
    config = parse_verification_config(SOURCE)
    assert config.version == 1
    assert isinstance(config.checks, tuple)
    assert [check.id for check in config.checks] == ["tests", "lint"]
    assert config.checks[0].command == " pytest -q "
    assert config.checks[1].command == "ruff check ."


@pytest.mark.parametrize(
    "source",
    [
        b"",
        b"version: 1\nchecks: [",
        b"\xff",
        b"version: 1\nchecks: !!python/object/apply:builtins.list []\n",
        b"version: 1\nversion: 1\nchecks: [{id: tests, command: pytest}]",
        b"version: 1\nchecks: [{id: tests, command: pytest, command: true}]",
    ],
)
def test_invalid_yaml_is_wrapped_with_source_context(source: bytes) -> None:
    with pytest.raises(VerificationConfigError) as caught:
        parse_verification_config(source)
    assert isinstance(caught.value, ValueError)
    assert caught.value.__cause__ is not None
    assert "shipyard.yaml" in str(caught.value)


@pytest.mark.parametrize(
    "updates",
    [
        {"version": 2},
        {"version": "1"},
        {"version": True},
        {"checks": []},
        {"checks": [{"id": "tests"}]},
        {"checks": [{"id": " tests", "command": "pytest"}]},
        {"checks": [{"id": "", "command": "pytest"}]},
        {"checks": [{"id": "tests", "command": " \n"}]},
        {"checks": [{"id": "tests", "command": True}]},
        {"checks": [{"id": 1, "command": "pytest"}]},
        {"checks": [{"id": "tests", "command": "pytest", "mandatory": False}]},
        {"checks": [{"id": "tests", "command": "pytest", "timeout": 10}]},
        {"checks": [{"id": "tests", "command": "pytest", "cwd": "."}]},
        {
            "checks": [
                {"id": "tests", "command": "pytest"},
                {"id": "tests", "command": "other"},
            ]
        },
        {"project": "unsupported"},
    ],
)
def test_schema_rejects_unsupported_or_ineffective_config(
    updates: dict[str, object],
) -> None:
    payload = {
        "version": 1,
        "checks": [{"id": "tests", "command": "pytest"}],
        **updates,
    }
    with pytest.raises(ValidationError):
        VerificationConfig.model_validate(payload)


def test_parser_wraps_schema_failure_without_echoing_source() -> None:
    source = b"version: 1\nchecks: [{id: tests, command: sensitive-command, unexpected: true}]"
    with pytest.raises(VerificationConfigError) as caught:
        parse_verification_config(source)
    assert isinstance(caught.value.__cause__, ValidationError)
    assert "sensitive-command" not in str(caught.value)


@pytest.mark.parametrize("field", ["version", "checks"])
def test_configuration_fields_are_required(field: str) -> None:
    payload = {"version": 1, "checks": [{"id": "tests", "command": "pytest"}]}
    del payload[field]
    with pytest.raises(ValidationError):
        VerificationConfig.model_validate(payload)


def test_snapshot_and_nested_settings_are_immutable_and_round_trip() -> None:
    config = parse_verification_config(SOURCE)
    snapshot = VerificationConfigSnapshot(
        base_sha="a" * 40, source_sha256="b" * 64, config=config
    )
    assert (
        VerificationConfigSnapshot.model_validate_json(snapshot.model_dump_json())
        == snapshot
    )
    for record, field in [
        (snapshot, "base_sha"),
        (snapshot.config, "version"),
        (snapshot.config.checks[0], "command"),
    ]:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(record, field, getattr(record, field))
    assert set(snapshot.model_dump()) == {"base_sha", "source_sha256", "config"}
