import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shipyard.cli import app
from shipyard.control.client import ControlClient
from shipyard.domain import RunContract
from tests.application.test_run_execution import capture


def test_run_submits_without_invoking_foreground_executor(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    calls: list[dict[str, object]] = []

    def request(
        self: ControlClient,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "POST" and path == "/runs"
        assert payload is not None
        calls.append(payload)
        return {"state": "QUEUED", "submission": payload}

    monkeypatch.setattr(ControlClient, "request", request)
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(contract.run_id),
            "--repo",
            str(repo.checkout_root()),
            "--runs-dir",
            str(store.directory(contract.run_id).parent),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["state"] == "QUEUED"
    assert len(calls) == 1
    assert calls[0]["run_id"] == str(contract.run_id)
    assert store.load_state(contract.run_id).lifecycle == "CREATED"


def test_unavailable_service_retains_created_run(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(contract.run_id),
            "--repo",
            str(repo.checkout_root()),
            "--runs-dir",
            str(store.directory(contract.run_id).parent),
            "--control-dir",
            str(tmp_path / "absent"),
        ],
    )
    assert result.exit_code == 1
    assert "service start" in result.output
    assert store.load_state(contract.run_id).lifecycle == "CREATED"
