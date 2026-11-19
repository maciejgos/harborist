"""Read-only reconciliation of packaged verification with immutable captures."""

import hashlib
from collections import Counter
from pathlib import Path
from uuid import UUID

from harborist.agents.base import AgentRequest
from harborist.application.review import evaluate_review, validate_test_context
from harborist.application.stages import StageExecution
from harborist.application.verification import TestExecution
from harborist.domain import RunLifecycle, RunOutcome
from harborist.domain.artifact import ArtifactKind, ArtifactStage
from harborist.domain.attempt import Attempt
from harborist.domain.stage_result import AgentStage, ReviewStageResult, StageStatus
from harborist.evidence.index import load_index
from harborist.evidence.package import RunEvidence
from harborist.persistence import FileRunStore
from harborist.skills.composition import compile_methodology, compose_guidance


def load_application_evidence(*, root: Path, run_id: UUID) -> RunEvidence:
    """Validate the index before consuming records; never inspect workspace HEAD."""
    store = FileRunStore(root=root).pinned(run_id)
    directory = store.directory(run_id)
    evidence, indexed = load_index(directory)

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
        or attempt.start_sha != store.attempt_start(run_id, contract.base_sha)
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
    required_stages = set(AgentStage)
    if evidence.reused_spec_sha256 is not None:
        from harborist.persistence.continuation import load_continuation

        read("continuation.json")
        read("continuation-context.json")
        record = load_continuation(store, run_id)
        raw_spec = read("frozen-spec.md")
        if (
            record.attempt != attempt
            or evidence.reused_spec_sha256 != record.spec_digest
            or hashlib.sha256(raw_spec).hexdigest() != record.spec_digest
        ):
            raise ValueError("Reused specification provenance mismatch")
        specification = raw_spec.decode()
        required_stages.remove(AgentStage.DESIGN)
    else:
        design = stages.get(AgentStage.DESIGN)
        specification = design.output.artifact if design is not None else None
    if (
        len(evidence.stages) != len(required_stages)
        or set(stages) != required_stages
        or specification is None
    ):
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
                and inputs.get("spec.md") != specification
            )
            or (
                stage.stage == AgentStage.BUILD
                and inputs.get("plan.md") != stages[AgentStage.PLAN].output.artifact
            )
        ):
            raise ValueError("Stage request attribution mismatch")
        if (
            stage.stage == AgentStage.PLAN
            and "continuation-context.json" in inputs
            and inputs["continuation-context.json"].encode()
            != read("continuation-context.json")
        ):
            raise ValueError("Continuation PLAN input differs from frozen context")
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
    review_stage = stages[AgentStage.REVIEW]
    review = review_stage.output.result
    if not isinstance(review, ReviewStageResult):
        raise ValueError("Independent REVIEW is required")  # noqa: TRY004
    request = AgentRequest.model_validate_json(read("review/request.json"))
    inputs = {i.name: i.content for i in request.inputs}
    if (
        inputs.get("spec.md") != specification
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
        specification=specification or "",
        review=review,
    )
    if (
        decision.verification != run.verification
        or decision != review_stage.review_decision
        or decision.outcome != RunOutcome.VERIFIED
    ):
        raise ValueError("Independent REVIEW conflicts with terminal verification")
    return evidence
