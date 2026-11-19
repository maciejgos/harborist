"""Immutable verification settings, without YAML or execution dependencies."""

from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from harborist.domain.artifact import ArtifactSha256
from harborist.domain.revision import GitCommitSha

type _NonemptyText = Annotated[str, StringConstraints(strict=True, min_length=1)]


class VerificationCheck(BaseModel):
    """One mandatory check; its command is opaque text until trusted execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: _NonemptyText
    command: _NonemptyText

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Check IDs must not have surrounding whitespace")
        return value

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Check commands must contain non-whitespace text")
        return value


class VerificationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Annotated[int, Field(strict=True)]
    checks: Annotated[tuple[VerificationCheck, ...], Field(min_length=1)]

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("Only verification configuration version 1 is supported")
        return value

    @model_validator(mode="after")
    def validate_unique_checks(self) -> Self:
        ids = [check.id for check in self.checks]
        if len(ids) != len(set(ids)):
            raise ValueError("Verification check IDs must be unique")
        return self


class VerificationConfigSnapshot(BaseModel):
    """Validated settings and declared source provenance, not verification evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_sha: GitCommitSha
    source_sha256: ArtifactSha256
    config: VerificationConfig
