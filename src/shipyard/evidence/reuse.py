"""Validate a completed DESIGN capture when worker loss prevented PACKAGE."""

import hashlib
from collections import Counter
from pathlib import Path

from shipyard.agents.base import AgentRequest
from shipyard.application.stages import StageExecution
from shipyard.domain import RunContract
from shipyard.domain.artifact import ArtifactKind, ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.stage_result import AgentStage, StageStatus
from shipyard.evidence.index import regular
from shipyard.persistence.workspace import load_selection
from shipyard.review.criteria import extract_criteria
from shipyard.skills.composition import compile_methodology, compose_guidance


def load_durable_spec(
    *,
    directory: Path,
    contract: RunContract,
    attempt: Attempt,
    inherited_digest: str | None,
) -> bytes | None:
    if inherited_digest is not None:
        raw = regular(directory / "frozen-spec.md")
        if hashlib.sha256(raw).hexdigest() != inherited_digest:
            raise ValueError("Inherited frozen spec digest mismatch")
        return raw
    stage_dir = directory / "design"
    if stage_dir.is_symlink():
        raise ValueError("DESIGN capture must not be a symlink")
    if not (stage_dir / "manifest.json").exists():
        return None
    capture = StageExecution.model_validate_json(regular(stage_dir / "manifest.json"))
    if (
        capture.run_id != contract.run_id
        or capture.attempt_id != attempt.attempt_id
        or capture.stage != AgentStage.DESIGN
        or capture.output.result.stage != AgentStage.DESIGN
        or capture.candidate is not None
        or capture.review_decision is not None
    ):
        raise ValueError("Interrupted DESIGN attribution mismatch")
    if capture.output.result.status != StageStatus.READY:
        raise ValueError("Only READY DESIGN may be reused")
    names = {
        "request.json": ArtifactKind.LOG,
        "stdout.log": ArtifactKind.LOG,
        "stderr.log": ArtifactKind.LOG,
        "invocation.json": ArtifactKind.LOG,
        "stage-result.json": ArtifactKind.STAGE_RESULT,
        "spec.md": ArtifactKind.SPEC,
    }
    captured = {name: regular(stage_dir / name) for name in names}
    expected = Counter(
        (kind, len(captured[name]), hashlib.sha256(captured[name]).hexdigest())
        for name, kind in names.items()
    )
    actual = Counter(
        (ref.kind, ref.size_bytes, ref.sha256) for ref in capture.artifacts
    )
    if expected != actual or any(
        ref.run_id != contract.run_id
        or ref.attempt_id != attempt.attempt_id
        or ref.produced_by != ArtifactStage.DESIGN
        for ref in capture.artifacts
    ):
        raise ValueError("Interrupted DESIGN artifact digest/ownership mismatch")
    request = AgentRequest.model_validate_json(captured["request.json"])
    selection = load_selection(directory, contract.run_id)
    if (
        request.stage != AgentStage.DESIGN
        or request.candidate is not None
        or request.profile != contract.execution.agent_profile
        or request.guidance
        != compose_guidance(
            compile_methodology(contract.execution), stage=ArtifactStage.DESIGN
        )
        or {item.name: item.content for item in request.inputs}
        != {"intent.md": contract.intent.markdown}
        or selection is None
        or selection.attempt_id != attempt.attempt_id
        or request.workspace != selection.path
        or captured["stage-result.json"].decode()
        != capture.output.result.model_dump_json()
        or captured["spec.md"].decode() != capture.output.artifact
    ):
        raise ValueError("Interrupted DESIGN does not match frozen invocation")
    extract_criteria(captured["spec.md"].decode())
    return captured["spec.md"]
