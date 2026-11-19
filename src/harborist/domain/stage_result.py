"""Validated agent declarations, separate from trusted stage execution state."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from harborist.domain.candidate import Candidate


class AgentStage(StrEnum):
    DESIGN = "design"
    PLAN = "plan"
    BUILD = "build"
    REVIEW = "review"


class StageStatus(StrEnum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_RESCOPING = "needs_rescoping"


class CriterionStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNVERIFIED = "unverified"


class CriterionResult(BaseModel):
    """An agent's assessment of one criterion, pending spec/evidence checks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: Annotated[str, StringConstraints(strict=True, min_length=1)]
    status: CriterionStatus

    @field_validator("criterion_id")
    @classmethod
    def validate_criterion_id(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Criterion IDs must not contain surrounding whitespace")
        return value


class ReviewSummary(BaseModel):
    """Counts derived from a review's criterion declarations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pass_count: Annotated[int, Field(strict=True, ge=0)]
    fail_count: Annotated[int, Field(strict=True, ge=0)]
    unverified_count: Annotated[int, Field(strict=True, ge=0)]


class DesignStageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: Literal[AgentStage.DESIGN]
    status: Literal[StageStatus.READY, StageStatus.NEEDS_CLARIFICATION]


class PlanStageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: Literal[AgentStage.PLAN]
    status: Literal[StageStatus.READY, StageStatus.NEEDS_RESCOPING]


class BuildStageResult(BaseModel):
    """BUILD readiness; Harborist creates and binds the Candidate later."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: Literal[AgentStage.BUILD]
    status: Literal[
        StageStatus.READY, StageStatus.NEEDS_CLARIFICATION, StageStatus.NEEDS_RESCOPING
    ]


class ReviewStageResult(BaseModel):
    """A finished assessment; even all-PASS declarations do not grant VERIFIED."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: Literal[AgentStage.REVIEW]
    status: Literal[StageStatus.READY]
    candidate: Candidate
    criteria: Annotated[tuple[CriterionResult, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_criteria(self) -> Self:
        ids = [criterion.criterion_id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Criterion IDs must be unique within a review")
        return self

    @property
    def summary(self) -> ReviewSummary:
        return ReviewSummary(
            pass_count=sum(
                item.status == CriterionStatus.PASS for item in self.criteria
            ),
            fail_count=sum(
                item.status == CriterionStatus.FAIL for item in self.criteria
            ),
            unverified_count=sum(
                item.status == CriterionStatus.UNVERIFIED for item in self.criteria
            ),
        )


type StageResult = Annotated[
    DesignStageResult | PlanStageResult | BuildStageResult | ReviewStageResult,
    Field(discriminator="stage"),
]

_STAGE_RESULT_ADAPTER = TypeAdapter(StageResult)


class InvalidStageOutput(ValueError):
    """Agent output does not satisfy the expected structured stage contract."""


def parse_stage_result(raw_json: str, expected_stage: AgentStage) -> StageResult:
    """Parse a complete JSON document without repair or inference from prose.

    Callers must separately check process success and artifact existence, match
    REVIEW's Candidate to trusted execution context, and validate spec coverage
    and evidence. This function does not accept or advance a stage execution.
    """
    try:
        result = _STAGE_RESULT_ADAPTER.validate_json(raw_json)
    except ValidationError as error:
        raise InvalidStageOutput("Invalid structured stage output") from error
    if result.stage != expected_stage:
        raise InvalidStageOutput(
            f"Expected {expected_stage} output, received {result.stage}"
        )
    return result
