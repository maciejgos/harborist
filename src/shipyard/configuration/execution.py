"""Capture operator-selected settings and local methodology without executing them."""

import hashlib
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from shipyard.configuration.yaml import UniqueKeySafeLoader
from shipyard.domain.execution import (
    AgentProfile,
    ExecutionBudget,
    ExecutionSnapshot,
    MethodologyAsset,
    Nonblank,
)


class SettingsError(ValueError):
    """Operator settings or their referenced assets could not be captured."""


class _AssetSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Nonblank
    version: Nonblank
    path: Nonblank


class _Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Annotated[int, Field(strict=True)]
    playbook: _AssetSource
    skills: tuple[_AssetSource, ...]
    agent_profile: AgentProfile
    sandbox_policy: Literal["trusted-local"]

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("Only settings version 1 is supported")
        return value


def _capture_asset(source: _AssetSource, directory: Path) -> MethodologyAsset:
    content = (directory / source.path).read_bytes()
    return MethodologyAsset(
        name=source.name,
        version=source.version,
        content=content.decode("utf-8"),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def load_execution_settings(
    *, path: Path, budget: ExecutionBudget | None = None
) -> ExecutionSnapshot:
    """Resolve paths beside settings; budget is supplied by Shipyard, never YAML."""
    try:
        path = path.resolve(strict=True)
        settings = _Settings.model_validate(
            yaml.load(path.read_bytes().decode("utf-8"), Loader=UniqueKeySafeLoader)
        )
        return ExecutionSnapshot(
            playbook=_capture_asset(settings.playbook, path.parent),
            skills=tuple(
                _capture_asset(skill, path.parent) for skill in settings.skills
            ),
            agent_profile=settings.agent_profile,
            sandbox_policy=settings.sandbox_policy,
            budget=budget
            if budget is not None
            else ExecutionBudget(total_seconds=1800, verification_reserve_seconds=300),
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise SettingsError(f"Cannot capture execution settings from {path}") from error
