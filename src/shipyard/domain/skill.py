"""Immutable skill scope and exact content identities, without workflow control."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shipyard.domain.artifact import ArtifactSha256
from shipyard.domain.execution import Nonblank
from shipyard.domain.stage_result import AgentStage


class MethodologyIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["playbook", "skill"]
    name: Nonblank
    version: Nonblank
    sha256: ArtifactSha256


class SkillMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Nonblank
    version: Nonblank
    description: Nonblank
    stages: Annotated[tuple[AgentStage, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if len(self.stages) != len(set(self.stages)):
            raise ValueError("Skill stage scope must be unique")
        return self
