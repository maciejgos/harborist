import hashlib
import json
from pathlib import Path

import pytest

from shipyard.agents.base import AgentRequest, AgentResponse
from shipyard.application.execution import execute_run
from shipyard.domain import RunContract
from shipyard.domain.stage_result import AgentStage
from tests.application.test_run_execution import FakeAgent, capture


@pytest.mark.parametrize(
    "check,mode,expected",
    [
        ("test -f requested.txt", "verified", "VERIFIED"),
        ("test -f requested.txt", "unverified", "CHANGES_REQUIRED"),
        ("exit 1", "verified", "TEST_FAILED"),
    ],
)
def test_durable_process_report_survives_truncated_logs_and_cannot_override_test(
    tmp_path: Path, frozen_contract: RunContract, check: str, mode: str, expected: str
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract, check=check)

    class ReportingAgent(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            response = super().execute(request)
            if request.stage == AgentStage.DESIGN and self.mode == "unverified":
                payload = json.loads(response.output)
                payload["artifact"] = (
                    "AC-001: Independently prove test-first execution history."
                )
                return response.model_copy(update={"output": json.dumps(payload)})
            if request.stage == AgentStage.BUILD:
                payload = json.loads(response.output)
                payload["process_report"] = {
                    "checks": [
                        {
                            "phase": "red",
                            "command": "test -f requested.txt",
                            "returncode": 1,
                            "output": "requested.txt absent",
                        },
                        {
                            "phase": "green",
                            "command": "test -f requested.txt",
                            "returncode": 0,
                            "output": "requested.txt present",
                        },
                    ],
                    "limitations": "Agent-reported execution; history is not independently attested.",
                }
                return AgentResponse(
                    returncode=0,
                    output=json.dumps(payload),
                    stderr="truncated diagnostics",
                    stderr_truncated=True,
                )
            if request.stage == AgentStage.REVIEW:
                process = next(
                    item for item in request.inputs if item.name == "build-process.json"
                )
                data = json.loads(process.content)
                assert data["provenance"] == "agent-reported"
                assert data["run_id"] == str(contract.run_id)
                assert data["report"]["checks"][0]["returncode"] == 1
            return response

    agent = ReportingAgent(mode)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=agent,
    )
    directory = store.directory(contract.run_id)
    process = directory / "build" / "build-process.json"
    assert process.is_file()
    assert "agent-reported" in (directory / "report.md").read_text()
    entry = next(
        item for item in result.files if item.path == "build/build-process.json"
    )
    assert entry.sha256 == hashlib.sha256(process.read_bytes()).hexdigest()
    assert result.run.outcome == expected
    if check == "exit 1":
        assert AgentStage.REVIEW not in agent.calls
    else:
        manifest = json.loads((directory / "review" / "manifest.json").read_text())
        assert manifest["process_evidence_sha256"] == entry.sha256
