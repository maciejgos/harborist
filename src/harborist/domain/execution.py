"""Frozen execution inputs; these records do not execute or compose methodology."""

import hashlib
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from harborist.domain.artifact import ArtifactSha256
from harborist.domain.sandbox import SandboxPolicy

type Nonblank = Annotated[
    str, StringConstraints(strict=True, pattern=r"^\S(?:[\s\S]*\S)?$")
]
type PositiveSeconds = Annotated[int, Field(strict=True, gt=0)]


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_seconds: PositiveSeconds
    verification_reserve_seconds: PositiveSeconds

    @model_validator(mode="after")
    def validate_reserve(self) -> Self:
        if self.verification_reserve_seconds >= self.total_seconds:
            raise ValueError("Verification reserve must be smaller than total budget")
        return self


class MethodologyAsset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Nonblank
    version: Nonblank
    content: Annotated[str, StringConstraints(strict=True, min_length=1)]
    sha256: ArtifactSha256

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Methodology content must not be blank")
        return value

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("Methodology digest must match content")
        return self


class AgentProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Nonblank
    version: Nonblank
    provider: Nonblank
    model: Nonblank
    arguments: tuple[Annotated[str, StringConstraints(strict=True)], ...]


class ExecutionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    playbook: MethodologyAsset
    skills: tuple[MethodologyAsset, ...]
    agent_profile: AgentProfile
    sandbox_policy: Literal["trusted-local"] | SandboxPolicy
    budget: ExecutionBudget

    @model_validator(mode="after")
    def validate_methodology(self) -> Self:
        if self.playbook.name != "bounded-repository-change":
            raise ValueError("PoC requires the bounded-repository-change playbook")
        names = [skill.name for skill in self.skills]
        if len(names) != len(set(names)):
            raise ValueError("Skill names must be unique")
        return self
