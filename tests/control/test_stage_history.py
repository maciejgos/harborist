import json
from pathlib import Path

import pytest

from shipyard.application.execution import execute_run
from shipyard.control.read_model import read_saved
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture


@pytest.mark.parametrize(
    "mode,check,stage,state,skipped",
    [
        ("verified", "test -f requested.txt", "review", "completed", None),
        ("verified", "exit 1", "test", "failed", "review"),
        ("changes", "test -f requested.txt", "review", "failed", None),
        ("clarify", "exit 0", "design", "needs_clarification", "plan"),
        ("failure", "exit 0", "design", "failed", "plan"),
        ("cancel", "exit 0", "design", "cancelled", "plan"),
    ],
)
def test_historical_timeline_recovers_recorded_stage_outcomes(
    tmp_path: Path,
    frozen_contract: RunContract,
    mode: str,
    check: str,
    stage: str,
    state: str,
    skipped: str | None,
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract, check)
    execute_run(
        store=store, run_id=contract.run_id, repository=repo, agent=FakeAgent(mode)
    )
    directory = store.directory(contract.run_id)
    before = {
        name: (directory / name).read_bytes()
        for name in ("run.json", "evidence.json", "report.md")
    }
    view = read_saved(directory.parent, contract.run_id)
    assert view.stages[stage].state == state
    assert view.stages["package"].state == "completed"
    assert view.stage_errors == {}
    if skipped:
        assert view.stages[skipped].state == "skipped"
    if mode == "verified" and check == "test -f requested.txt":
        assert all(
            view.stages[name].state == "completed"
            for name in ("design", "plan", "build", "test", "review", "package")
        )
    assert before == {name: (directory / name).read_bytes() for name in before}


def test_missing_or_foreign_manifest_does_not_inherit_completion(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    execute_run(store=store, run_id=contract.run_id, repository=repo, agent=FakeAgent())
    directory = store.directory(contract.run_id)
    (directory / "plan" / "manifest.json").unlink()
    manifest = directory / "design" / "manifest.json"
    payload = json.loads(manifest.read_bytes())
    payload["attempt_id"] = "00000000-0000-4000-8000-000000000099"
    manifest.write_text(json.dumps(payload))
    view = read_saved(directory.parent, contract.run_id)
    assert "plan" not in view.stages
    assert "design" not in view.stages
    assert view.stage_errors["design"]
    assert view.stages["test"].state == "completed"
    assert view.run is not None and view.run.outcome == "VERIFIED"


def test_package_for_a_different_candidate_cannot_complete_the_timeline(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    execute_run(store=store, run_id=contract.run_id, repository=repo, agent=FakeAgent())
    directory = store.directory(contract.run_id)
    path = directory / "evidence.json"
    payload = json.loads(path.read_bytes())
    payload["candidate"]["candidate_sha"] = "f" * 40
    path.write_text(json.dumps(payload))
    view = read_saved(directory.parent, contract.run_id)
    assert "package" not in view.stages
    assert view.stage_errors["package"]
    assert view.stages["test"].state == "completed"
