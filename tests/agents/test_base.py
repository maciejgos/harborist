import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shipyard.agents.base import AgentInput, AgentRequest, output_schema, parse_output
from shipyard.configuration.execution import load_execution_settings
from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.execution import AgentProfile
from shipyard.domain.stage_result import AgentStage, InvalidStageOutput
from shipyard.skills.composition import compile_methodology, compose_guidance
from tests.settings_helpers import write_settings


def request(root: Path, stage: AgentStage = AgentStage.DESIGN) -> AgentRequest:
    snapshot = load_execution_settings(path=write_settings(root))
    return AgentRequest(
        stage=stage,
        workspace=root,
        profile=AgentProfile(
            name="test", version="1", provider="codex", model="test", arguments=()
        ),
        guidance=compose_guidance(
            compile_methodology(snapshot), stage=ArtifactStage(stage)
        ),
        inputs=(AgentInput(name="intent.md", content="Do the thing"),),
        timeout_seconds=10,
    )


def test_output_requires_artifact_and_exact_stage(tmp_path: Path) -> None:
    req = request(tmp_path)
    raw = json.dumps(
        {
            "result": {"stage": "design", "status": "ready"},
            "artifact": "# Spec",
            "plan_update": None,
        }
    )
    assert parse_output(raw, req).artifact == "# Spec"
    assert AgentRequest.model_validate_json(req.model_dump_json()) == req
    assert output_schema(req.stage)["additionalProperties"] is False
    for bad in (raw.replace("# Spec", "  "), raw.replace("design", "plan"), "{}"):
        with pytest.raises(InvalidStageOutput):
            parse_output(bad, req)


def test_request_rejects_missing_upstream_and_foreign_guidance(tmp_path: Path) -> None:
    req = request(tmp_path)
    data = req.model_dump()
    data["stage"] = AgentStage.BUILD
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(data)
    data = req.model_dump()
    data["candidate"] = {"attempt_id": uuid4(), "candidate_sha": "a" * 40}
    with pytest.raises(ValidationError):
        AgentRequest.model_validate(data)


def test_only_build_may_report_development_checks(tmp_path: Path) -> None:
    req = request(tmp_path)
    raw = json.dumps(
        {
            "result": {"stage": "design", "status": "ready"},
            "artifact": "AC-001: Product behavior",
            "plan_update": None,
            "process_report": {"checks": [], "limitations": "No tests"},
        }
    )
    with pytest.raises(InvalidStageOutput):
        parse_output(raw, req)


def test_build_revision_and_review_candidate(tmp_path: Path) -> None:
    from shipyard.domain.candidate import Candidate

    req = request(tmp_path)
    compiled = compile_methodology(
        load_execution_settings(path=tmp_path / "settings.yaml")
    )
    build = AgentRequest(
        stage=AgentStage.BUILD,
        workspace=tmp_path,
        profile=req.profile,
        guidance=compose_guidance(compiled, stage=ArtifactStage.BUILD),
        inputs=tuple(
            AgentInput(name=name, content="text")
            for name in ("intent.md", "spec.md", "plan.md")
        ),
        timeout_seconds=10,
    )
    raw = json.dumps(
        {
            "result": {"stage": "build", "status": "needs_rescoping"},
            "artifact": None,
            "plan_update": "# New plan",
        }
    )
    assert parse_output(raw, build).plan_update == "# New plan"
    candidate = Candidate(attempt_id=uuid4(), candidate_sha="a" * 40)
    review = AgentRequest(
        stage=AgentStage.REVIEW,
        workspace=tmp_path,
        profile=req.profile,
        guidance=compose_guidance(compiled, stage=ArtifactStage.REVIEW),
        inputs=tuple(
            AgentInput(name=name, content="text")
            for name in ("spec.md", "test-evidence.json")
        ),
        candidate=candidate,
        timeout_seconds=10,
    )
    result = {
        "stage": "review",
        "status": "ready",
        "candidate": candidate.model_dump(mode="json"),
        "criteria": [{"criterion_id": "AC-001", "status": "unverified"}],
    }
    raw = json.dumps({"result": result, "artifact": "# Review", "plan_update": None})
    assert parse_output(raw, review).result.stage == AgentStage.REVIEW
    with pytest.raises(InvalidStageOutput):
        parse_output(raw.replace("a" * 40, "b" * 40), review)
