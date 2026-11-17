"""Run presentation uses packaged facts and leaves detailed evidence on disk."""

import errno
import json
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from shipyard.agents import codex
from shipyard.application import execution
from shipyard.cli import app
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture
from tests.cli.conftest import strip_ansi


@pytest.mark.parametrize(
    "mode,check,status,lifecycle,outcome,checks,acceptance",
    [
        ("verified", "exit 0", 0, "COMPLETED", "VERIFIED", "1/1 passed", "1/1 passed"),
        (
            "verified",
            "exit 1",
            2,
            "COMPLETED",
            "TEST_FAILED",
            "0/1 passed",
            "unavailable (1 required)",
        ),
        (
            "changes",
            "exit 0",
            2,
            "COMPLETED",
            "CHANGES_REQUIRED",
            "1/1 passed",
            "0/1 passed",
        ),
        (
            "unverified",
            "exit 0",
            2,
            "COMPLETED",
            "CHANGES_REQUIRED",
            "1/1 passed",
            "0/1 passed",
        ),
        (
            "clarify",
            "exit 0",
            2,
            "COMPLETED",
            "NEEDS_CLARIFICATION",
            "unavailable (1 required)",
            "unavailable (total unknown)",
        ),
        (
            "failure",
            "exit 0",
            1,
            "FAILED",
            "EXECUTION_FAILED",
            "unavailable (1 required)",
            "unavailable (total unknown)",
        ),
        (
            "cancel",
            "exit 0",
            130,
            "CANCELLED",
            "CANCELLED",
            "unavailable (1 required)",
            "unavailable (total unknown)",
        ),
    ],
)
def test_default_summary(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    check: str,
    status: int,
    lifecycle: str,
    outcome: str,
    checks: str,
    acceptance: str,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract, check)
    monkeypatch.setattr(codex, "CodexAgent", lambda: FakeAgent(mode))
    result = CliRunner().invoke(
        app,
        [
            "run",
            "--foreground",
            str(contract.run_id),
            "--repo",
            str(tmp_path / "repository"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == status, result.output
    text = result.stdout
    assert f"ID: {contract.run_id}" in text
    assert f"Status: {lifecycle}" in text
    assert outcome in text
    assert f"Checks: {checks}" in text
    assert f"Acceptance: {acceptance}" in text
    directory = store.directory(contract.run_id)
    evidence = json.loads((directory / "evidence.json").read_text())
    if evidence["candidate"]:
        assert f"Candidate: {evidence['candidate']['candidate_sha']}" in text
    else:
        assert "Candidate: unavailable" in text
    assert "has not applied" in text
    assert f"Report: {directory.resolve() / 'report.md'}" in text
    assert f"Evidence: {directory.resolve() / 'evidence.json'}" in text
    assert len(text.splitlines()) <= 15
    for hidden in (
        "AC-001",
        '"verification"',
        contract.verification.source_sha256,
        "\x1b",
        "\r",
        "PACKAGE started",
    ):
        assert hidden not in text
    assert ("shipyard apply" in text) == (outcome == "VERIFIED")
    assert "PACKAGE started" in result.stderr
    assert "PACKAGE completed" in result.stderr


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("interrupted", [False, True])
def test_partial_package_failure_does_not_advertise_artifacts(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    json_mode: bool,
    interrupted: bool,
) -> None:
    store, _, contract = capture(tmp_path, frozen_contract)
    monkeypatch.setattr(codex, "CodexAgent", lambda: FakeAgent("clarify"))

    def broken(**kwargs: object) -> None:
        (store.directory(contract.run_id) / "report.md").write_text("partial")
        if interrupted:
            raise KeyboardInterrupt
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(execution, "package_run", broken)
    args = [
        "run",
        "--foreground",
        str(contract.run_id),
        "--repo",
        str(tmp_path / "repository"),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]
    result = CliRunner().invoke(app, args + (["--json"] if json_mode else []))
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "PACKAGE" in result.stderr
    assert "terminal artifacts unavailable" in result.stderr
    assert "Report:" not in result.stderr and "Evidence:" not in result.stderr
    if not interrupted:
        assert "No space left on device" in result.stderr


def test_run_help_describes_formats() -> None:
    result = CliRunner().invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    text = strip_ansi(result.stdout)
    assert "--json" in text
    assert "summary" in text
    assert "scripts" in text.lower()


def test_output_selection_only_renders_packaged_evidence(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both modes consume the same result, including legacy unknown workspace."""
    store, repo, contract = capture(tmp_path, frozen_contract)
    evidence = execution.execute_run(
        store=store, run_id=contract.run_id, repository=repo, agent=FakeAgent()
    ).model_copy(update={"workspace": None})
    directory = store.directory(contract.run_id)
    before = {
        name: (directory / name).read_bytes()
        for name in ("evidence.json", "report.md", "contract.json")
    }
    calls: list[dict[str, object]] = []

    def returned(**kwargs: object) -> object:
        calls.append(kwargs)
        return evidence

    monkeypatch.setattr(execution, "execute_run", returned)
    args = [
        "run",
        "--foreground",
        str(contract.run_id),
        "--repo",
        str(tmp_path / "repository"),
        "--runs-dir",
        str(tmp_path / "runs"),
    ]
    summary = CliRunner().invoke(app, args)
    structured = CliRunner().invoke(app, args + ["--json"])
    assert summary.exit_code == structured.exit_code == 0
    assert len(calls) == 2
    assert "Checks: 1/1 passed" in summary.stdout
    payload = json.loads(structured.stdout)
    assert payload == {
        "run": evidence.run.model_dump(mode="json"),
        "workspace": None,
        "report": str(directory.resolve() / "report.md"),
        "evidence": str(directory.resolve() / "evidence.json"),
    }
    assert before == {name: (directory / name).read_bytes() for name in before}


def test_unvalidated_evidence_is_unavailable(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from shipyard.cli.run_summary import render_summary
    from shipyard.domain.stage_result import AgentStage

    store, repo, contract = capture(tmp_path, frozen_contract)
    evidence = execution.execute_run(
        store=store, run_id=contract.run_id, repository=repo, agent=FakeAgent()
    )
    directory = store.directory(contract.run_id)
    # A REVIEW-shaped agent payload alone cannot establish an acceptance pass.
    stages = tuple(
        stage.model_copy(update={"review_decision": None})
        if stage.stage == AgentStage.REVIEW
        else stage
        for stage in evidence.stages
    )
    text = render_summary(evidence.model_copy(update={"stages": stages}), directory)
    assert "Acceptance: unavailable (1 required)" in text
    # A TEST result from another Run cannot contribute passes to this Run.
    assert evidence.test is not None

    foreign_test = evidence.test.model_copy(update={"run_id": uuid4()})
    text = render_summary(evidence.model_copy(update={"test": foreign_test}), directory)
    assert "Checks: unavailable (1 required)" in text
    assert "Acceptance: unavailable (1 required)" in text
    # Only files actually present are listed, even for a returned evidence object.
    (directory / "evidence.json").unlink()
    text = render_summary(evidence, directory)
    assert "Report:" in text and "Evidence:" not in text
