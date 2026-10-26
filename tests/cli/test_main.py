"""CLI acceptance: durable intake is explicit and never implies execution."""

import json
from pathlib import Path

from typer.testing import CliRunner

from shipyard.cli import app
from shipyard.domain import RunContract
from tests.git_helpers import git, init_repository
from tests.settings_helpers import write_settings

runner = CliRunner()


def test_intake_and_inspect_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "target"
    init_repository(target)
    (target / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: tests, command: pytest}]\n"
    )
    git(target, "add", "shipyard.yaml")
    git(target, "commit", "-m", "Config")
    issue = tmp_path / "issue.md"
    issue.write_text("Fix it")
    settings = write_settings(tmp_path)
    runs = tmp_path / "runs"
    result = runner.invoke(
        app,
        [
            "intake",
            f"file:{issue}",
            "--repo",
            str(target),
            "--settings",
            str(settings),
            "--runs-dir",
            str(runs),
            "--timeout",
            "900",
            "--verification-reserve",
            "100",
        ],
    )
    assert result.exit_code == 0, result.output
    contract = RunContract.model_validate_json(result.stdout)
    assert contract.execution.budget.total_seconds == 900
    assert contract.execution.budget.verification_reserve_seconds == 100
    issue.unlink()
    settings.unlink()
    inspected = runner.invoke(
        app, ["inspect", str(contract.run_id), "--runs-dir", str(runs)]
    )
    assert inspected.exit_code == 0, inspected.output
    assert json.loads(inspected.stdout) == json.loads(result.stdout)


def test_expected_failures_are_nonzero_without_tracebacks(tmp_path: Path) -> None:
    settings = write_settings(tmp_path)
    result = runner.invoke(
        app,
        [
            "intake",
            "file:missing.md",
            "--repo",
            str(tmp_path),
            "--settings",
            str(settings),
        ],
    )
    assert result.exit_code == 1
    assert "Cannot resolve Git" in result.stderr
    assert "Traceback" not in result.output
    result = runner.invoke(
        app,
        [
            "intake",
            "file:missing.md",
            "--settings",
            str(settings),
            "--timeout",
            "100",
            "--verification-reserve",
            "100",
        ],
    )
    assert result.exit_code == 1
    assert "reserve" in result.stderr
    result = runner.invoke(
        app,
        [
            "inspect",
            "00000000-0000-4000-8000-000000000001",
            "--runs-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "Cannot load Run" in result.stderr


def test_saved_methodology_preview_is_frozen_and_stage_scoped(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from shipyard.persistence import FileRunStore
    from tests.methodology_helpers import skill_asset

    contract = RunContract.model_validate(
        {
            **frozen_contract.model_dump(),
            "execution": {
                **frozen_contract.execution.model_dump(),
                "skills": [skill_asset()],
            },
        }
    )
    store = FileRunStore(root=tmp_path)
    store.save(contract)
    path = tmp_path / str(contract.run_id) / "contract.json"
    before = path.read_bytes()
    args = [str(contract.run_id), "--runs-dir", str(tmp_path)]
    result = runner.invoke(app, ["methodology", *args])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.stdout)
    assert len(preview["playbook"]["definition"]["stages"]) == 7
    assert preview["skills"][0]["identity"]["name"] == "engineering"
    result = runner.invoke(app, ["methodology", *args, "--stage", "build"])
    assert result.exit_code == 0, result.output
    assert (
        json.loads(result.stdout)["skills"][0]["content"]
        == "# Engineering\nFollow the acceptance contract.\n"
    )
    result = runner.invoke(app, ["methodology", *args, "--stage", "test"])
    assert result.exit_code == 1
    assert "agent stage" in result.stderr
    assert path.read_bytes() == before


def test_legacy_inspection_still_works_but_compilation_reports_error(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from shipyard.persistence import FileRunStore
    from tests.methodology_helpers import asset

    legacy = RunContract.model_validate(
        {
            **frozen_contract.model_dump(),
            "execution": {
                **frozen_contract.execution.model_dump(),
                "playbook": asset(
                    name="bounded-repository-change",
                    version="1",
                    content="# Legacy guidance",
                ),
            },
        }
    )
    FileRunStore(root=tmp_path).save(legacy)
    args = [str(legacy.run_id), "--runs-dir", str(tmp_path)]
    assert runner.invoke(app, ["inspect", *args]).exit_code == 0
    result = runner.invoke(app, ["methodology", *args])
    assert result.exit_code == 1
    assert "Cannot compile playbook" in result.stderr
    assert "Traceback" not in result.output
