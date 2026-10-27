"""Synchronous stage invocation contract; no provider or session state."""

from pathlib import Path
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from shipyard.domain.candidate import Candidate
from shipyard.domain.execution import AgentProfile
from shipyard.domain.guidance import StageGuidance
from shipyard.domain.stage_result import (
    AgentStage,
    BuildStageResult,
    DesignStageResult,
    InvalidStageOutput,
    PlanStageResult,
    ReviewStageResult,
    StageResult,
)
from shipyard.domain.usage import Usage

REQUIRED_INPUTS: dict[AgentStage, frozenset[str]] = {
    AgentStage.DESIGN: frozenset({"intent.md"}),
    AgentStage.PLAN: frozenset({"intent.md", "spec.md"}),
    AgentStage.BUILD: frozenset({"intent.md", "spec.md", "plan.md"}),
    AgentStage.REVIEW: frozenset({"spec.md", "test-evidence.json"}),
}


class AgentInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: Literal["intent.md", "spec.md", "plan.md", "test-evidence.json"]
    content: Annotated[str, Field(strict=True, min_length=1)]

    @model_validator(mode="after")
    def nonblank(self) -> Self:
        if not self.content.strip():
            raise ValueError("Upstream artifact must not be blank")
        return self


class AgentRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: AgentStage
    workspace: Path
    profile: AgentProfile
    guidance: StageGuidance
    inputs: tuple[AgentInput, ...]
    timeout_seconds: Annotated[int, Field(strict=True, gt=0)]
    candidate: Candidate | None = None

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        names = [item.name for item in self.inputs]
        if len(names) != len(set(names)) or not REQUIRED_INPUTS[self.stage] <= set(
            names
        ):
            raise ValueError("Missing or duplicate upstream artifacts")
        if self.guidance.stage != self.stage:
            raise ValueError("Guidance must match requested stage")
        if (self.stage == AgentStage.REVIEW) != (self.candidate is not None):
            raise ValueError("Only REVIEW requires an exact candidate")
        return self


class AgentResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    returncode: int
    output: str
    usage: Usage | None = None
    stdout: Annotated[str, Field(max_length=196608)] = ""
    stderr: Annotated[str, Field(max_length=196608)] = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class AgentOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    result: StageResult
    artifact: str | None
    plan_update: str | None


class NativeAgent(Protocol):
    def execute(self, request: AgentRequest) -> AgentResponse:
        """Start one fresh invocation; never resume a previous agent session."""
        ...


class AgentExecutionError(RuntimeError):
    """Provider launch, deadline or process failure; not a software outcome."""

    def __init__(self, message: str, *, response: AgentResponse | None = None) -> None:
        super().__init__(message)
        self.response = response


def parse_output(raw: str, request: AgentRequest) -> AgentOutput:
    try:
        output = AgentOutput.model_validate_json(raw)
        if output.result.stage != request.stage:
            raise ValueError("Wrong stage")
        if request.stage != AgentStage.BUILD:
            if output.artifact is None or not output.artifact.strip():
                raise ValueError("Missing required Markdown artifact")
            if output.plan_update is not None:
                raise ValueError("Only BUILD may revise plan.md")
        elif output.artifact is not None:
            raise ValueError("BUILD has no separate Markdown artifact")
        if output.plan_update is not None and not output.plan_update.strip():
            raise ValueError("Plan revision must not be blank")
        if (
            isinstance(output.result, ReviewStageResult)
            and output.result.candidate != request.candidate
        ):
            raise ValueError("REVIEW candidate does not match execution context")
        return output
    except (ValidationError, ValueError) as error:
        raise InvalidStageOutput("Invalid structured stage output") from error


def output_schema(stage: AgentStage) -> dict[str, object]:
    """Schema has one concrete result type for the selected stage."""
    model = {
        AgentStage.DESIGN: DesignStageResult,
        AgentStage.PLAN: PlanStageResult,
        AgentStage.BUILD: BuildStageResult,
        AgentStage.REVIEW: ReviewStageResult,
    }[stage]
    result = model.model_json_schema()
    definitions = result.pop("$defs", {})
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "result": result,
            "artifact": {"type": ["string", "null"]},
            "plan_update": {"type": ["string", "null"]},
        },
        "required": ["result", "artifact", "plan_update"],
        "$defs": definitions,
    }
