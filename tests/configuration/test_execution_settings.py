"""Freeze actual methodology bytes and operator-controlled execution settings."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from shipyard.configuration import SettingsError, load_execution_settings
from shipyard.domain.execution import ExecutionBudget, ExecutionSnapshot
from tests.settings_helpers import write_settings


def test_freezes_content_and_ignores_later_settings_changes(tmp_path: Path) -> None:
    path = write_settings(tmp_path)
    snapshot = load_execution_settings(path=path)
    assert snapshot.playbook.name == "bounded-repository-change"
    assert snapshot.skills[0].content.encode() == (tmp_path / "skill.md").read_bytes()
    assert (
        snapshot.skills[0].sha256
        == hashlib.sha256((tmp_path / "skill.md").read_bytes()).hexdigest()
    )
    assert snapshot.budget == ExecutionBudget(
        total_seconds=1800, verification_reserve_seconds=300
    )
    serialized = snapshot.model_dump_json()
    path.unlink()
    (tmp_path / "skill.md").write_text("Changed")
    assert ExecutionSnapshot.model_validate_json(serialized) == snapshot
    with pytest.raises(ValidationError, match="digest"):
        ExecutionSnapshot.model_validate(
            {
                **snapshot.model_dump(),
                "playbook": {**snapshot.playbook.model_dump(), "content": "tampered"},
            }
        )


@pytest.mark.parametrize(
    "change", ["duplicate", "budget", "version", "skill", "missing"]
)
def test_settings_fail_closed(tmp_path: Path, change: str) -> None:
    path = write_settings(tmp_path)
    text = path.read_text()
    if change == "duplicate":
        text += "version: 1\n"
    elif change == "budget":
        text += "budget: {total_seconds: 9999}\n"
    elif change == "version":
        text = text.replace("version: 1", "version: 2", 1)
    elif change == "skill":
        text = text.replace(
            "skills: [", "skills: [{name: engineering, version: '2', path: skill.md}, "
        )
    else:
        (tmp_path / "skill.md").unlink()
    path.write_text(text)
    with pytest.raises(SettingsError) as caught:
        load_execution_settings(path=path)
    assert caught.value.__cause__ is not None


def test_explicit_operator_budget_is_captured(tmp_path: Path) -> None:
    path = write_settings(tmp_path)
    budget = ExecutionBudget(total_seconds=900, verification_reserve_seconds=100)
    assert load_execution_settings(path=path, budget=budget).budget == budget
