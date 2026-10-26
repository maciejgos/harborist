"""Execute one independent agent stage and capture validated durable artifacts."""

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
    NativeAgent,
    parse_output,
)
from shipyard.domain.artifact import ArtifactKind, ArtifactReference, ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.playbook_execution import StageReceipt, StepOutcome
from shipyard.domain.run_contract import RunContract
from shipyard.domain.stage_result import AgentStage, InvalidStageOutput
from shipyard.git.repository import GitRepository
from shipyard.skills.composition import compile_methodology, compose_guidance


class StageExecution(BaseModel):
    """Completed capture, not a lifecycle transition or verification grant."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: UUID
    attempt_id: UUID
    stage: AgentStage
    candidate: Candidate | None
    output: AgentOutput
    artifacts: tuple[ArtifactReference, ...]


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
    TEST evidence. No candidate commit or software outcome is created here.
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
    if set(upstream) - REQUIRED_INPUTS[stage] or not required <= set(upstream):
        raise ValueError("Provide exactly the required durable upstream artifacts")
    before = {name: path.read_bytes() for name, path in upstream.items()}
    if "intent.md" in before and before["intent.md"] != contract.intent.markdown.encode(
        "utf-8"
    ):
        raise ValueError("Upstream intent must match frozen contract")
    inputs = [AgentInput(name="intent.md", content=contract.intent.markdown)]
    for name in sorted(required):
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
        if (
            test_receipt is None
            or test_receipt.stage != ArtifactStage.TEST
            or test_receipt.outcome != StepOutcome.SUCCEEDED
            or test_receipt.candidate != candidate
        ):
            raise ValueError("REVIEW requires successful TEST for the exact candidate")
        assert candidate is not None  # AgentRequest enforces this binding.
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
    response = agent.execute(request)
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
    execution = StageExecution(
        run_id=contract.run_id,
        attempt_id=attempt.attempt_id,
        stage=stage,
        candidate=candidate,
        output=output,
        artifacts=tuple(artifacts),
    )
    with (output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(execution.model_dump_json())
    return execution
