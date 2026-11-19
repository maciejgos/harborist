import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harborist.application.execution import execute_run
from harborist.cli import app
from harborist.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture


def test_foreground_rework_reports_latest_attempt_and_can_apply(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    first = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent("changes"),
    )
    monkeypatch.setattr("harborist.cli.continuation.CodexAgent", lambda: FakeAgent())
    root = store.directory(contract.run_id).parent
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "rework",
            str(contract.run_id),
            "--repo",
            str(repo.checkout_root()),
            "--runs-dir",
            str(root),
            "--foreground",
            "--json",
            "--feedback",
            "Fix AC-001",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["run"]["outcome"] == "VERIFIED"
    assert "attempts/000001/report.md" in payload["report"]
    assert first.attempt is not None
    assert payload["attempt"]["attempt_id"] != str(first.attempt.attempt_id)
    applied = runner.invoke(
        app,
        [
            "apply",
            str(contract.run_id),
            "--repo",
            str(repo.checkout_root()),
            "--runs-dir",
            str(root),
            "--branch",
            "main",
        ],
    )
    assert applied.exit_code == 0, applied.output


def test_background_continuation_uses_service_and_returns_acceptance(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harborist.control.queue import QueueStore
    from harborist.control.service import ControlService

    store, repo, contract = capture(tmp_path, frozen_contract)
    root = store.directory(contract.run_id).parent
    execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "first",
        agent=FakeAgent("changes"),
    )
    agent = FakeAgent()
    service = ControlService(
        QueueStore(tmp_path / "control"), agent=agent, history_root=root
    )

    def request(
        self: object, method: str, path: str, payload: dict[str, object] | None = None
    ) -> dict[str, object]:
        return service.dispatch(method, path, json.dumps(payload).encode())

    monkeypatch.setattr("harborist.cli.continuation.ControlClient.request", request)
    result = CliRunner().invoke(
        app,
        [
            "rework",
            str(contract.run_id),
            "--repo",
            str(repo.checkout_root()),
            "--runs-dir",
            str(root),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["state"] == "QUEUED"
    assert agent.calls == []
    assert service.worker.execute_next()
    view = service.history.get(contract.run_id)
    assert view.run is not None and view.run.outcome == "VERIFIED"
    assert view.attempt_number == 1
