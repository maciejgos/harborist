import json

import pytest
from typer.testing import CliRunner

from harborist.cli import app
from harborist.control.client import ControlClient

RUN_ID = "00000000-0000-4000-8000-000000000001"


def test_wait_reads_until_terminal_without_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots: list[dict[str, object]] = [
        {"state": "RUNNING", "submission": {"run_id": RUN_ID}},
        {
            "state": "FINISHED",
            "submission": {"run_id": RUN_ID},
            "run": {"outcome": "CHANGES_REQUIRED"},
        },
    ]
    responses = iter(snapshots)

    def request(
        self: ControlClient,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "GET"
        assert path == f"/runs/{RUN_ID}"
        return next(responses)

    monkeypatch.setattr(ControlClient, "request", request)
    result = CliRunner().invoke(
        app, ["status", RUN_ID, "--wait", "--interval", "0.01", "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["state"] == "FINISHED"


def test_list_human_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def request(
        self: ControlClient,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert method == "GET" and path == "/runs"
        return {
            "runs": [
                {
                    "state": "INTERRUPTED",
                    "submission": {"run_id": RUN_ID},
                    "error": "Service ownership lost",
                }
            ]
        }

    monkeypatch.setattr(ControlClient, "request", request)
    result = CliRunner().invoke(app, ["runs"])
    assert result.exit_code == 0, result.output
    assert RUN_ID in result.stdout
    assert "INTERRUPTED" in result.stdout
    assert "Service ownership lost" in result.stdout


def test_status_human_summary_shows_outcome_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def request(
        self: ControlClient,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "state": "FINISHED",
            "submission": {"run_id": RUN_ID},
            "run": {"lifecycle": "COMPLETED", "outcome": "CHANGES_REQUIRED"},
            "progress": {"stage": "package", "state": "completed"},
            "package_available": True,
            "artifacts": {"report.md": "/runs/report.md"},
        }

    monkeypatch.setattr(ControlClient, "request", request)
    result = CliRunner().invoke(app, ["status", RUN_ID])
    assert result.exit_code == 0, result.output
    assert "Outcome: CHANGES_REQUIRED" in result.stdout
    assert "Progress: PACKAGE completed" in result.stdout
    assert "report.md: /runs/report.md" in result.stdout


def test_wait_returns_for_terminal_saved_run_without_delivery_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def request(
        self: ControlClient,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "state": None,
            "source": "saved",
            "submission": {"run_id": RUN_ID},
            "run": {"lifecycle": "COMPLETED", "outcome": "VERIFIED"},
        }

    monkeypatch.setattr(ControlClient, "request", request)

    def no_wait(seconds: float) -> None:
        raise AssertionError("Terminal saved Run must not keep polling")

    monkeypatch.setattr("harborist.cli.monitoring.time.sleep", no_wait)
    result = CliRunner().invoke(app, ["status", RUN_ID, "--wait"])
    assert result.exit_code == 0, result.output
    assert "VERIFIED" in result.stdout
    assert "Delivery: None" not in result.stdout
