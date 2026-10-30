"""Read-only reconciliation of packaged verification with immutable captures."""

import hashlib
import stat
from collections import Counter
from pathlib import Path, PurePosixPath
from uuid import UUID

from shipyard.agents.base import AgentRequest
from shipyard.application.review import evaluate_review, validate_test_context
from shipyard.application.stages import StageExecution
from shipyard.application.verification import TestExecution
from shipyard.domain import RunLifecycle, RunOutcome
from shipyard.domain.artifact import ArtifactKind, ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.stage_result import AgentStage, ReviewStageResult, StageStatus
from shipyard.evidence.package import RunEvidence
from shipyard.persistence import FileRunStore
from shipyard.skills.composition import compile_methodology, compose_guidance


def _regular(path: Path) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"Evidence must be a regular file: {path}")
    return path.read_bytes()


def load_application_evidence(*, root: Path, run_id: UUID) -> RunEvidence:
    """Validate the index before consuming records; never inspect workspace HEAD."""
    directory = root / str(run_id)
    if directory.is_symlink():
        raise ValueError("Run directory must not be a symlink")
    evidence = RunEvidence.model_validate_json(_regular(directory / "evidence.json"))
    if evidence.version != 1:
        raise ValueError("Unsupported evidence version")
    indexed: dict[str, bytes] = {}
    for entry in evidence.files:
        relative = PurePosixPath(entry.path)
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != entry.path
            or entry.path in indexed
            or relative.parts[0] == "workspace"
            or entry.path == "evidence.json"
        ):
            raise ValueError(f"Unsafe or duplicate evidence path: {entry.path}")
        path = directory
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                raise ValueError(f"Evidence symlink: {path}")
        raw = _regular(path)
        if (
            len(raw) != entry.size_bytes
            or hashlib.sha256(raw).hexdigest() != entry.sha256
        ):
            raise ValueError(f"Evidence length/digest mismatch: {entry.path}")
        indexed[entry.path] = raw

    def read(name: str) -> bytes:
        if name not in indexed:
            raise ValueError(f"Required immutable record missing from index: {name}")
        return indexed[name]

    for name in (
        "run.json",
        "contract.json",
        "events.jsonl",
        "intent.json",
        "intent.md",
        "attempt.json",
        "report.md",
    ):
        read(name)
    for name in (
        "workspace-layout.json",
        "execution-context.json",
        "execution-workspace.json",
    ):
        if (directory / name).exists() or (directory / name).is_symlink():
            read(name)
    store = FileRunStore(root=root)
    contract = store.load(run_id)
    run = store.load_state(run_id)
    attempt = Attempt.model_validate_json(read("attempt.json"))
    candidate = evidence.candidate
    test = evidence.test
    if (
        run.lifecycle != RunLifecycle.COMPLETED
        or run.outcome != RunOutcome.VERIFIED
        or run.verification is None
        or evidence.run != run
        or evidence.contract != contract
        or evidence.attempt != attempt
        or attempt.run_id != run_id
        or attempt.start_sha != contract.base_sha
        or candidate is None
        or test is None
        or candidate != run.verification.candidate
        or attempt != run.verification.attempt
        or candidate.attempt_id != attempt.attempt_id
        or evidence.error is not None
    ):
        raise ValueError(
            "Application requires consistent packaged COMPLETED/VERIFIED evidence"
        )
    persisted_test = TestExecution.model_validate_json(read("test/manifest.json"))
    if persisted_test != test or not validate_test_context(
        contract=contract, attempt=attempt, candidate=candidate, test=test
    ):
        raise ValueError("Application requires complete passing TEST evidence")
    for index, check in enumerate(test.collection.checks):
        for stream, captured in (
            ("stdout", check.stdout_path),
            ("stderr", check.stderr_path),
        ):
            name = f"test/logs/{index:04d}.{stream}.log"
            read(name)
            if Path(captured) != directory / name:
                raise ValueError("TEST log path attribution mismatch")
    stages = {s.stage: s for s in evidence.stages}
    if len(evidence.stages) != 4 or set(stages) != set(AgentStage):
        raise ValueError(
            "Application requires complete canonical native-stage captures"
        )
    methodology = compile_methodology(contract.execution)
    for stage in evidence.stages:
        prefix = stage.stage.value
        if (
            stage.run_id != run_id
            or stage.attempt_id != attempt.attempt_id
            or stage.output.result.stage != stage.stage
            or stage.output.result.status != StageStatus.READY
            or stage.candidate
            != (candidate if stage.stage == AgentStage.REVIEW else None)
            or StageExecution.model_validate_json(read(f"{prefix}/manifest.json"))
            != stage
        ):
            raise ValueError("Stage identity/capture conflicts with packaged evidence")
        request = AgentRequest.model_validate_json(read(f"{prefix}/request.json"))
        inputs = {i.name: i.content for i in request.inputs}
        if (
            request.stage != stage.stage
            or request.candidate != stage.candidate
            or request.profile != contract.execution.agent_profile
            or request.guidance
            != compose_guidance(methodology, stage=ArtifactStage(stage.stage))
            or inputs.get("intent.md") != contract.intent.markdown
            or (
                stage.stage != AgentStage.DESIGN
                and inputs.get("spec.md") != stages[AgentStage.DESIGN].output.artifact
            )
            or (
                stage.stage == AgentStage.BUILD
                and inputs.get("plan.md") != stages[AgentStage.PLAN].output.artifact
            )
        ):
            raise ValueError("Stage request attribution mismatch")
        names = {
            "request.json": ArtifactKind.LOG,
            "stdout.log": ArtifactKind.LOG,
            "stderr.log": ArtifactKind.LOG,
            "invocation.json": ArtifactKind.LOG,
            "stage-result.json": ArtifactKind.STAGE_RESULT,
        }
        if stage.output.artifact is not None:
            kind = {
                AgentStage.DESIGN: ArtifactKind.SPEC,
                AgentStage.PLAN: ArtifactKind.PLAN,
                AgentStage.REVIEW: ArtifactKind.REVIEW,
            }[stage.stage]
            names[f"{kind.value}.md"] = kind
        if stage.output.plan_update is not None:
            names["plan.md"] = ArtifactKind.PLAN
        if stage.output.process_report is not None:
            names["build-process.json"] = ArtifactKind.LOG
        expected = Counter(
            (kind, len(raw), hashlib.sha256(raw).hexdigest())
            for name, kind in names.items()
            for raw in [read(f"{prefix}/{name}")]
        )
        actual = Counter((a.kind, a.size_bytes, a.sha256) for a in stage.artifacts)
        if expected != actual or len({a.artifact_id for a in stage.artifacts}) != len(
            stage.artifacts
        ):
            raise ValueError(
                "Stage artifact references must cover complete persisted capture"
            )
        if (
            read(f"{prefix}/stage-result.json").decode()
            != stage.output.result.model_dump_json()
        ):
            raise ValueError("Persisted stage result differs from packaged result")
        for artifact in stage.artifacts:
            if (
                artifact.run_id != run_id
                or artifact.attempt_id != attempt.attempt_id
                or artifact.produced_by.value != prefix
                or not any(
                    name.startswith(prefix + "/")
                    and len(raw) == artifact.size_bytes
                    and hashlib.sha256(raw).hexdigest() == artifact.sha256
                    for name, raw in indexed.items()
                )
            ):
                raise ValueError("Stage artifact ownership or content mismatch")
        artifact_name = {
            "design": "spec.md",
            "plan": "plan.md",
            "review": "review.md",
        }.get(prefix)
        if (
            artifact_name
            and read(f"{prefix}/{artifact_name}").decode() != stage.output.artifact
        ):
            raise ValueError("Stage Markdown differs from packaged artifact")
        if (
            stage.output.plan_update is not None
            and read(f"{prefix}/plan.md").decode() != stage.output.plan_update
        ):
            raise ValueError("BUILD plan update mismatch")
    design = stages[AgentStage.DESIGN]
    review_stage = stages[AgentStage.REVIEW]
    review = review_stage.output.result
    if not isinstance(review, ReviewStageResult):
        raise ValueError("Independent REVIEW is required")  # noqa: TRY004
    request = AgentRequest.model_validate_json(read("review/request.json"))
    inputs = {i.name: i.content for i in request.inputs}
    if (
        inputs.get("spec.md") != design.output.artifact
        or inputs.get("test-evidence.json", "").encode() != read("test/manifest.json")
        or review_stage.test_evidence_sha256
        != hashlib.sha256(read("test/manifest.json")).hexdigest()
    ):
        raise ValueError("REVIEW inputs must match exact DESIGN and TEST captures")
    if "build-process.json" in inputs:
        raw = read("build/build-process.json")
        if (
            inputs["build-process.json"].encode() != raw
            or review_stage.process_evidence_sha256 != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("REVIEW BUILD process attribution mismatch")
    decision = evaluate_review(
        contract=contract,
        attempt=attempt,
        candidate=candidate,
        test=test,
        specification=design.output.artifact or "",
        review=review,
    )
    if (
        decision.verification != run.verification
        or decision != review_stage.review_decision
        or decision.outcome != RunOutcome.VERIFIED
    ):
        raise ValueError("Independent REVIEW conflicts with terminal verification")
    return evidence
