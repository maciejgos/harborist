"""Run contracts bind existing frozen inputs without performing intake."""

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from harborist.domain import (
    IntentSnapshot,
    RunContract,
    VerificationCheck,
    VerificationConfig,
    VerificationConfigSnapshot,
)
from harborist.domain.execution import ExecutionSnapshot


@pytest.fixture
def contract(execution: ExecutionSnapshot) -> RunContract:
    run_id = UUID("00000000-0000-4000-8000-000000000001")
    intent = IntentSnapshot.create(
        run_id=run_id,
        source_ref="file:/issue.md",
        markdown="\ufeff# Café\r\nPreserve this request.\r\n",
    )
    verification = VerificationConfigSnapshot(
        base_sha="a" * 40,
        source_sha256="b" * 64,
        config=VerificationConfig(
            version=1,
            checks=(
                VerificationCheck(id="tests", command=" pytest -q "),
                VerificationCheck(id="lint", command="ruff check ."),
            ),
        ),
    )
    return RunContract(
        run_id=run_id,
        intent=intent,
        base_sha="a" * 40,
        verification=verification,
        execution=execution,
    )


def test_composition_preserves_supplied_snapshots(contract: RunContract) -> None:
    composed = RunContract(
        run_id=contract.run_id,
        intent=contract.intent,
        base_sha=contract.base_sha,
        verification=contract.verification,
        execution=contract.execution,
    )
    assert composed.intent is contract.intent
    assert composed.verification is contract.verification
    assert composed == contract
    assert set(composed.model_dump()) == {
        "run_id",
        "intent",
        "base_sha",
        "verification",
        "execution",
    }


@pytest.mark.parametrize(
    "updates,message",
    [
        ({"run_id": "00000000-0000-4000-8000-000000000002"}, "Run ownership"),
        ({"base_sha": "c" * 40}, "base SHA"),
    ],
)
def test_inconsistent_bindings_rejected_in_construction_and_json(
    contract: RunContract, updates: dict[str, str], message: str
) -> None:
    payload = {**contract.model_dump(mode="json"), **updates}
    with pytest.raises(ValidationError, match=message):
        RunContract.model_validate(payload)
    with pytest.raises(ValidationError, match=message):
        RunContract.model_validate_json(json.dumps(payload))


def test_equivalent_mapping_order_and_round_trip_are_deterministic(
    contract: RunContract,
) -> None:
    # Reverse every mapping's input order, including nested snapshot metadata.
    reordered = json.loads(
        contract.model_dump_json(),
        object_pairs_hook=lambda pairs: dict(reversed(pairs)),
    )
    rebuilt = RunContract.model_validate(reordered)
    serialized = contract.model_dump_json()
    assert rebuilt.model_dump_json() == serialized
    assert RunContract.model_validate_json(serialized) == contract
    assert rebuilt.intent.markdown == "\ufeff# Café\r\nPreserve this request.\r\n"
    assert [check.id for check in rebuilt.verification.config.checks] == [
        "tests",
        "lint",
    ]
    assert rebuilt.verification.config.checks[0].command == " pytest -q "


def test_contract_and_nested_snapshot_are_frozen(contract: RunContract) -> None:
    with pytest.raises(ValidationError, match="frozen"):
        contract.base_sha = "c" * 40
    with pytest.raises(ValidationError, match="frozen"):
        contract.intent.markdown = "Changed intent"


def test_unknown_contract_fields_are_rejected(contract: RunContract) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RunContract.model_validate({**contract.model_dump(), "profile": "future"})


def test_execution_snapshot_is_required(contract: RunContract) -> None:
    payload = contract.model_dump()
    del payload["execution"]
    with pytest.raises(ValidationError, match="execution"):
        RunContract.model_validate(payload)
