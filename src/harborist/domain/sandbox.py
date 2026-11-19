"""Frozen local execution policy; no Docker process or filesystem dependencies."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CODEX_KIT = "docker.io/sbx/codex@sha256:7d283f7cacf5c069b6f61cdcba87ce3b570a0c5a43c36d88d3f8873732503162"


class SandboxPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    kind: Literal["docker-sandboxes"] = "docker-sandboxes"
    template: Annotated[
        str, Field(pattern=r"^[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}$")
    ] = CODEX_KIT
    cpus: Annotated[int, Field(strict=True, ge=1, le=16)] = 2
    memory_mib: Annotated[int, Field(strict=True, ge=512, le=32768)] = 2048
    allow: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    deny: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    baseline_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    @field_validator("allow", "deny")
    @classmethod
    def network_resources(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for value in values:
            value = value.strip().lower()
            if not re.fullmatch(
                r"(?:\*\*?\.)?[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?", value
            ):
                raise ValueError(
                    "Use a hostname, optional wildcard subdomain, and optional port"
                )
            host, _, port = value.partition(":")
            if ".." in host or (port and not 1 <= int(port) <= 65535):
                raise ValueError("Invalid network destination")
            if value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    @model_validator(mode="after")
    def distinct_rules(self) -> Self:
        if set(self.allow) & set(self.deny):
            raise ValueError(
                "A destination cannot appear in both allowed and blocked rules"
            )
        return self
