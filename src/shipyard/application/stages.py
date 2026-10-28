"""Execute one independent agent stage and capture validated durable artifacts."""

import hashlib
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shipyard.agents.base import (
    REQUIRED_INPUTS,
    AgentExecutionError,
    AgentInput,
    AgentOutput,
    AgentRequest,
    AgentResponse,
    NativeAgent,
    parse_output,
)
from shipyard.application.review import (
    ReviewDecision,
    evaluate_review,
    validate_test_context,
)
from shipyard.application.verification import TestExecution
from shipyard.domain.artifact import ArtifactKind, ArtifactReference, ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.build_process import BuildProcessEvidence
from shipyard.domain.candidate import Candidate
from shipyard.domain.playbook_execution import StageReceipt, StepOutcome
from shipyard.domain.run_contract import RunContract
from shipyard.domain.stage_result import (
    AgentStage,
    InvalidStageOutput,
    ReviewStageResult,
)
from shipyard.domain.usage import Usage
from shipyard.git.repository import GitRepository
from shipyard.review.criteria import extract_criteria
from shipyard.skills.composition import compile_methodology, compose_guidance


class StageExecution(BaseModel):
    """Completed capture with a harness decision for validated REVIEW."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: UUID
    attempt_id: UUID
    stage: AgentStage
    candidate: Candidate | None
    output: AgentOutput
    artifacts: tuple[ArtifactReference, ...]
    review_decision: ReviewDecision | None = None
    test_evidence_sha256: str | None = None
    process_evidence_sha256: str | None = None
    usage: Usage | None = None


def execute_stage(
    *,
    contract: RunContract,
    attempt: Attempt,
    stage: AgentStage,
    workspace: Path,
    upstream: Mapping[str, Path],
    output_dir: Path,
    agent: NativeAgent,
    remaining_seconds: int,
    candidate: Candidate | None = None,
    test_receipt: StageReceipt | None = None,
) -> StageExecution:
    """Use explicit durable input versions; retain partial directories on failure.

    The caller owns workspace isolation, remaining budget calculation and trusted
    TEST captures. REVIEW returns a validated decision; the caller owns Run
    completion and persistence. No candidate commit is created here.
    """
    if attempt.run_id != contract.run_id:
        raise ValueError("Attempt must belong to the frozen Run")
    if candidate is not None and candidate.attempt_id != attempt.attempt_id:
        raise ValueError("Candidate must belong to the executing Attempt")
    workspace = workspace.resolve(strict=True)
    output_dir = output_dir.resolve()
    if not workspace.is_dir() or output_dir.is_relative_to(workspace):
        raise ValueError("Output directory must be outside the repository workspace")
    required = REQUIRED_INPUTS[stage] - {"intent.md"}
    allowed = set(REQUIRED_INPUTS[stage])
    if stage == AgentStage.REVIEW:
        allowed.add("build-process.json")
    if set(upstream) - allowed or not required <= set(upstream):
        raise ValueError("Provide exactly the required durable upstream artifacts")
    before = {name: path.read_bytes() for name, path in upstream.items()}
    if "intent.md" in before and before["intent.md"] != contract.intent.markdown.encode(
        "utf-8"
    ):
        raise ValueError("Upstream intent must match frozen contract")
    inputs = [AgentInput(name="intent.md", content=contract.intent.markdown)]
    for name in sorted(set(before) - {"intent.md"}):
        # Names were checked against the fixed stage contract above.
        inputs.append(
            AgentInput.model_validate(
                {"name": name, "content": before[name].decode("utf-8")}
            )
        )
    request = AgentRequest(
        stage=stage,
        workspace=workspace,
        profile=contract.execution.agent_profile,
        guidance=compose_guidance(
            compile_methodology(contract.execution), stage=ArtifactStage(stage)
        ),
        inputs=tuple(inputs),
        timeout_seconds=remaining_seconds,
        candidate=candidate,
    )
    if stage == AgentStage.REVIEW:
        if "build-process.json" in before:
            process = BuildProcessEvidence.model_validate_json(
                before["build-process.json"]
            )
            if (
                process.run_id != contract.run_id
                or process.attempt_id != attempt.attempt_id
            ):
                raise ValueError(
                    "BUILD process evidence must belong to the executing Attempt"
                )
        if (
            test_receipt is None
            or test_receipt.stage != ArtifactStage.TEST
            or test_receipt.outcome != StepOutcome.SUCCEEDED
            or test_receipt.candidate != candidate
        ):
            raise ValueError("REVIEW requires successful TEST for the exact candidate")
        assert candidate is not None  # AgentRequest enforces this binding.
        test_capture = TestExecution.model_validate_json(before["test-evidence.json"])
        if test_capture.receipt != test_receipt or not validate_test_context(
            contract=contract, attempt=attempt, candidate=candidate, test=test_capture
        ):
            raise ValueError("REVIEW requires successful complete TEST evidence")
        extract_criteria(before["spec.md"].decode("utf-8"))
        GitRepository(path=workspace).require_clean_revision(
            commit_sha=candidate.candidate_sha
        )
    elif test_receipt is not None:
        raise ValueError("Only REVIEW consumes a TEST receipt")

    output_dir.mkdir()
    artifacts: list[ArtifactReference] = []

    def save(name: str, content: str, kind: ArtifactKind) -> None:
        raw = content.encode("utf-8")
        with (output_dir / name).open("xb") as stream:
            stream.write(raw)
        artifacts.append(
            ArtifactReference.create(
                run_id=contract.run_id,
                attempt_id=attempt.attempt_id,
                kind=kind,
                produced_by=ArtifactStage(stage),
                content=raw,
            )
        )

    save("request.json", request.model_dump_json(), ArtifactKind.LOG)

    def save_diagnostics(response: AgentResponse) -> None:
        save("stdout.log", response.stdout, ArtifactKind.LOG)
        save("stderr.log", response.stderr, ArtifactKind.LOG)
        save(
            "invocation.json",
            response.model_dump_json(exclude={"output", "stdout", "stderr"}),
            ArtifactKind.LOG,
        )

    try:
        response = agent.execute(request)
    except AgentExecutionError as error:
        if error.response is not None:
            save_diagnostics(error.response)
        raise
    save_diagnostics(response)
    try:
        unchanged = all(
            path.read_bytes() == before[name] for name, path in upstream.items()
        )
    except OSError as error:
        raise InvalidStageOutput(
            "Upstream artifact disappeared during invocation"
        ) from error
    if not unchanged:
        raise InvalidStageOutput("Upstream artifacts changed during invocation")
    if stage == AgentStage.REVIEW:
        assert candidate is not None
        GitRepository(path=workspace).require_clean_revision(
            commit_sha=candidate.candidate_sha
        )
    if response.returncode != 0:
        raise AgentExecutionError(
            f"Native agent exited with code {response.returncode}"
        )
    output = parse_output(response.output, request)
    decision = None
    if isinstance(output.result, ReviewStageResult):
        assert candidate is not None
        decision = evaluate_review(
            contract=contract,
            attempt=attempt,
            candidate=candidate,
            specification=before["spec.md"].decode("utf-8"),
            review=output.result,
            test=TestExecution.model_validate_json(before["test-evidence.json"]),
        )
    save(
        "stage-result.json", output.result.model_dump_json(), ArtifactKind.STAGE_RESULT
    )
    if output.artifact is not None:
        kind = {
            AgentStage.DESIGN: ArtifactKind.SPEC,
            AgentStage.PLAN: ArtifactKind.PLAN,
            AgentStage.REVIEW: ArtifactKind.REVIEW,
        }[stage]
        save(f"{kind.value}.md", output.artifact, kind)
    if output.plan_update is not None:
        save("plan.md", output.plan_update, ArtifactKind.PLAN)
    if output.process_report is not None:
        process = BuildProcessEvidence(
            run_id=contract.run_id,
            attempt_id=attempt.attempt_id,
            report=output.process_report,
        )
        save("build-process.json", process.model_dump_json(), ArtifactKind.LOG)
    execution = StageExecution(
        run_id=contract.run_id,
        attempt_id=attempt.attempt_id,
        stage=stage,
        candidate=candidate,
        output=output,
        artifacts=tuple(artifacts),
        review_decision=decision,
        usage=response.usage,
        test_evidence_sha256=hashlib.sha256(before["test-evidence.json"]).hexdigest()
        if stage == AgentStage.REVIEW
        else None,
        process_evidence_sha256=hashlib.sha256(before["build-process.json"]).hexdigest()
        if "build-process.json" in before
        else None,
    )
    with (output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(execution.model_dump_json())
    return execution
