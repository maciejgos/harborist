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


def test_source_capture_submits_once_and_retains_frozen_context(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    from shipyard.control.queue import QueueStore, Submission
    from tests.settings_helpers import write_settings

    store, repo, _ = capture(tmp_path, frozen_contract)
    source = tmp_path / "issue.md"
    source.write_text("Implement a bounded change")
    queue = QueueStore(tmp_path / "control")

    def request(
        self: ControlClient,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "POST" and path == "/runs"
        return queue.submit(Submission.model_validate(payload)).model_dump(mode="json")

    monkeypatch.setattr(ControlClient, "request", request)
    result = CliRunner().invoke(
        app,
        [
            "run",
            f"file:{source}",
            "--repo",
            str(repo.checkout_root()),
            "--settings",
            str(write_settings(tmp_path)),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    record = json.loads(result.stdout)
    run_id = UUID(record["submission"]["run_id"])
    assert record["state"] == "QUEUED"
    assert len(queue.list()) == 1
    assert store.load(run_id).intent.markdown == "Implement a bounded change"
    assert (store.directory(run_id) / "execution-context.json").is_file()
    assert not (store.directory(run_id) / ".execution").exists()
