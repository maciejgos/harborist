"""Run progress stays on stderr and never exposes failing boundary payloads."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shipyard.agents import codex
from shipyard.application import execution
from shipyard.cli import app
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture


@pytest.mark.parametrize(
    "mode,check,status,reason",
    [
        ("verified", "exit 0", 0, "VERIFIED"),
        ("clarify", "exit 0", 2, "NEEDS_CLARIFICATION"),
        ("verified", "exit 1", 2, "TEST_FAILED"),
        ("failure", "exit 0", 1, "EXECUTION_FAILED"),
        ("cancel", "exit 0", 130, "CANCELLED"),
    ],
)
def test_cli_streams_and_preserves_terminal_json(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    check: str,
    status: int,
    reason: str,
) -> None:
    _, _, contract = capture(tmp_path, frozen_contract, check)

    monkeypatch.setattr(codex, "CodexAgent", lambda: FakeAgent(mode))
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(contract.run_id),
            "--repo",
            str(tmp_path / "repository"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--workspace",
            str(tmp_path / "work"),
        ],
    )
    assert result.exit_code == status, result.output
    payload = json.loads(result.stdout)
    assert set(payload) == {"run", "report", "evidence"}
    assert Path(payload["report"]).is_absolute() and Path(payload["report"]).is_file()
    assert (
        Path(payload["evidence"]).is_absolute() and Path(payload["evidence"]).is_file()
    )
    assert result.stderr.startswith(f"Run: {contract.run_id}\n")
    assert f"Result: {reason}" in result.stderr
    assert "PACKAGE completed" in result.stderr
    assert "\x1b" not in result.stderr and "\r" not in result.stderr
    if reason == "TEST_FAILED":
        assert "TEST failed" in result.stderr
        assert "REVIEW skipped" in result.stderr
        assert "REVIEW started" not in result.stderr


@pytest.mark.parametrize(
    "boundary,mode",
    [("package_run", "clarify"), ("package_run", "cancel"), ("finish", "clarify")],
)
def test_cli_finalization_failure_is_safe(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    mode: str,
) -> None:
    from shipyard.persistence import FileRunStore

    _, _, contract = capture(tmp_path, frozen_contract)
    monkeypatch.setattr(codex, "CodexAgent", lambda: FakeAgent(mode))

    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("SECRET raw diagnostic")

    monkeypatch.setattr(
        execution if boundary == "package_run" else FileRunStore, boundary, broken
    )
    result = CliRunner().invoke(
        app,
        [
            "run",
            str(contract.run_id),
            "--repo",
            str(tmp_path / "repository"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--workspace",
            str(tmp_path / "work"),
        ],
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "failed; terminal artifacts unavailable" in result.stderr
    assert "SECRET" not in result.stderr
    assert "PACKAGE completed" not in result.stderr
    assert "Report:" not in result.stderr
