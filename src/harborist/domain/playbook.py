"""Canonical workflow topology and executor authority, without execution."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harborist.domain.artifact import ArtifactStage
from harborist.domain.execution import Nonblank


class ExecutorType(StrEnum):
    HARBORIST = "harborist"
    NATIVE_AGENT = "native_agent"
    TRUSTED_TEST = "trusted_test"

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        # Existing playbooks and frozen Runs still contain this executor name.
        return cls.HARBORIST if value == "shipyard" else None


type _StrictBool = Annotated[bool, Field(strict=True)]

_ORDER = (
    ArtifactStage.INTAKE,
    ArtifactStage.DESIGN,
    ArtifactStage.PLAN,
    ArtifactStage.BUILD,
    ArtifactStage.TEST,
    ArtifactStage.REVIEW,
    ArtifactStage.PACKAGE,
)


class StageDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: ArtifactStage
    executor: ExecutorType
    depends_on: tuple[ArtifactStage, ...]
    fresh_invocation: _StrictBool
    read_only: _StrictBool
    budgeted: _StrictBool


def _canonical_stages() -> tuple[StageDefinition, ...]:
    steps: list[StageDefinition] = []
    for index, stage in enumerate(_ORDER):
        agent = stage in (
            ArtifactStage.DESIGN,
            ArtifactStage.PLAN,
            ArtifactStage.BUILD,
            ArtifactStage.REVIEW,
        )
        executor = ExecutorType.NATIVE_AGENT if agent else ExecutorType.HARBORIST
        if stage == ArtifactStage.TEST:
            executor = ExecutorType.TRUSTED_TEST
        steps.append(
            StageDefinition(
                stage=stage,
                executor=executor,
                depends_on=() if index == 0 else (_ORDER[index - 1],),
                fresh_invocation=agent,
                read_only=stage == ArtifactStage.REVIEW,
                budgeted=stage != ArtifactStage.PACKAGE,
            )
        )
    return tuple(steps)


class PlaybookDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Literal["bounded-repository-change"]
    version: Nonblank
    stages: tuple[StageDefinition, ...]

    @model_validator(mode="after")
    def validate_canonical_topology(self) -> Self:
        if self.stages != _canonical_stages():
            raise ValueError(
                "Playbook must preserve canonical stages, dependencies and authority"
            )
        return self


def canonical_playbook(*, version: str) -> PlaybookDefinition:
    """Build the single supported topology with an explicit methodology version."""
    return PlaybookDefinition(
        name="bounded-repository-change", version=version, stages=_canonical_stages()
    )
