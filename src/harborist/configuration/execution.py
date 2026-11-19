"""Capture operator-selected settings and local methodology without executing them."""

import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from harborist.agents.codex import (
    CODEX_MODEL_PATTERN,
    ReasoningEffort,
    validate_profile,
)
from harborist.configuration.yaml import UniqueKeySafeLoader
from harborist.domain.execution import (
    AgentProfile,
    ExecutionBudget,
    ExecutionSnapshot,
    MethodologyAsset,
    Nonblank,
)
from harborist.domain.sandbox import SandboxPolicy


class SettingsError(ValueError):
    """Operator settings or their referenced assets could not be captured."""


def execution_settings_path(checkout: Path, settings: Path | None) -> Path:
    if settings is not None:
        return settings
    current = checkout / "harborist.settings.yaml"
    previous = checkout / "shipyard.settings.yaml"
    return (
        previous
        if not current.exists() and not current.is_symlink() and previous.is_file()
        else current
    )


class CodexProfileSetup(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    model: Annotated[str, Field(strict=True, pattern=f"^{CODEX_MODEL_PATTERN}$")]
    effort: ReasoningEffort | None = None


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
    sandbox_policy: Literal["trusted-local"] | SandboxPolicy

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


def _read_settings(path: Path) -> object:
    return yaml.load(path.read_bytes().decode("utf-8"), Loader=UniqueKeySafeLoader)


def codex_profile_status(path: Path) -> dict[str, object]:
    try:
        profile = _Settings.model_validate(_read_settings(path)).agent_profile
        effort = validate_profile(profile)
    except OSError:
        return {
            "status": "settings_unavailable",
            "message": "The execution settings file could not be read.",
        }
    except ValidationError, UnicodeError, yaml.YAMLError:
        return {
            "status": "invalid_profile",
            "message": "Check the execution settings YAML and its agent_profile section.",
        }
    except ValueError as error:
        return {"status": "invalid_profile", "message": str(error)}
    return {
        "status": "configured",
        "message": "Codex profile is configured.",
        "model": profile.model,
        "effort": effort,
    }


def configure_codex_profile(path: Path, setup: CodexProfileSetup) -> None:
    try:
        path = path.resolve(strict=True)
        raw = _read_settings(path)
        if not isinstance(raw, dict):
            raise TypeError("Expected execution settings")
        settings = cast(dict[str, object], raw)
        current = settings.get("agent_profile")
        profile = cast(dict[str, object], current) if isinstance(current, dict) else {}
        settings["agent_profile"] = {
            "name": profile.get("name", "local-codex"),
            "version": profile.get("version", "1"),
            "provider": "codex",
            "model": setup.model,
            "arguments": ["-c", f'model_reasoning_effort="{setup.effort}"']
            if setup.effort
            else [],
        }
        validated = _Settings.model_validate(settings)
        validate_profile(validated.agent_profile)
        with NamedTemporaryFile(
            dir=path.parent, mode="w", encoding="utf-8", delete=False
        ) as stream:
            pending = Path(stream.name)
            try:
                yaml.safe_dump(settings, stream, sort_keys=False, allow_unicode=True)
                stream.close()
                pending.replace(path)
            finally:
                pending.unlink(missing_ok=True)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        raise SettingsError(
            "Could not save the Codex profile. Check the execution settings file and its permissions."
        ) from error


def load_execution_settings(
    *, path: Path, budget: ExecutionBudget | None = None
) -> ExecutionSnapshot:
    """Resolve paths beside settings; budget is supplied by Harborist, never YAML."""
    try:
        path = path.resolve(strict=True)
        settings = _Settings.model_validate(_read_settings(path))
        validate_profile(settings.agent_profile)
        policy = settings.sandbox_policy
        if isinstance(policy, SandboxPolicy):
            from harborist.sandbox.docker import DockerSandboxRuntime

            policy = policy.model_copy(
                update={"baseline_sha256": DockerSandboxRuntime().baseline_digest()}
            )
        return ExecutionSnapshot(
            playbook=_capture_asset(settings.playbook, path.parent),
            skills=tuple(
                _capture_asset(skill, path.parent) for skill in settings.skills
            ),
            agent_profile=settings.agent_profile,
            sandbox_policy=policy,
            budget=budget
            if budget is not None
            else ExecutionBudget(total_seconds=1800, verification_reserve_seconds=300),
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise SettingsError(f"Cannot capture execution settings from {path}") from error


def sandbox_policy_status(path: Path) -> dict[str, object]:
    try:
        policy = _Settings.model_validate(_read_settings(path)).sandbox_policy
    except OSError, ValueError, yaml.YAMLError:
        return {
            "status": "settings_unavailable",
            "message": "Cannot read valid execution settings.",
        }
    return {
        "status": "configured",
        "policy": policy.model_dump(mode="json")
        if isinstance(policy, SandboxPolicy)
        else policy,
    }


def configure_sandbox_policy(
    path: Path, policy: Literal["trusted-local"] | SandboxPolicy
) -> None:
    """Save future execution defaults without provisioning or changing Docker globals."""
    try:
        path = path.resolve(strict=True)
        raw = _read_settings(path)
        if not isinstance(raw, dict):
            raise TypeError("Expected settings mapping")
        settings = cast(dict[str, object], raw)
        settings["sandbox_policy"] = (
            policy.model_copy(update={"baseline_sha256": None}).model_dump(mode="json")
            if isinstance(policy, SandboxPolicy)
            else policy
        )
        _Settings.model_validate(settings)
        with NamedTemporaryFile(
            dir=path.parent, mode="w", encoding="utf-8", delete=False
        ) as stream:
            pending = Path(stream.name)
            try:
                yaml.safe_dump(settings, stream, sort_keys=False, allow_unicode=True)
                stream.close()
                pending.replace(path)
            finally:
                pending.unlink(missing_ok=True)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        raise SettingsError(
            "Could not save sandbox policy. Check the execution settings file and permissions."
        ) from error
