"""Execution declarations freeze meaningful policy without executing it."""

import pytest
from pydantic import ValidationError

from harborist.domain import ExecutionBudget, ExecutionSnapshot


@pytest.mark.parametrize(
    "total,reserve", [(0, 1), (100, 100), (100, 101), (100, 0), (True, 1)]
)
def test_budget_requires_positive_seconds_and_room_for_build(
    total: int, reserve: int
) -> None:
    with pytest.raises(ValidationError):
        ExecutionBudget(total_seconds=total, verification_reserve_seconds=reserve)


def test_asset_digest_is_bound_to_exact_content(execution: ExecutionSnapshot) -> None:
    payload = execution.model_dump()
    payload["playbook"]["content"] = "Tampered content"
    with pytest.raises(ValidationError, match="digest"):
        ExecutionSnapshot.model_validate(payload)


def test_canonical_playbook_and_unique_skills(execution: ExecutionSnapshot) -> None:
    asset = execution.playbook.model_dump()
    with pytest.raises(ValidationError, match="bounded-repository-change"):
        ExecutionSnapshot.model_validate(
            {**execution.model_dump(), "playbook": {**asset, "name": "other"}}
        )
    with pytest.raises(ValidationError, match="unique"):
        ExecutionSnapshot.model_validate(
            {**execution.model_dump(), "skills": [asset, asset]}
        )


def test_snapshot_is_frozen_and_complete(execution: ExecutionSnapshot) -> None:
    assert (
        ExecutionSnapshot.model_validate_json(execution.model_dump_json()) == execution
    )
    with pytest.raises(ValidationError, match="frozen"):
        execution.agent_profile.model = "changed"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExecutionSnapshot.model_validate({**execution.model_dump(), "future": True})
