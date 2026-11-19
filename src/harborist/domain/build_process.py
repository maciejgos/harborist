"""Bounded BUILD declarations; these are not trusted check receipts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type _Command = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=2048, pattern=r"\S")
]
type _Excerpt = Annotated[str, StringConstraints(strict=True, max_length=8192)]


class ReportedCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal["red", "green"]
    command: _Command
    returncode: Annotated[int, Field(strict=True)]
    output: _Excerpt


class BuildProcessReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checks: Annotated[tuple[ReportedCheck, ...], Field(max_length=12)]
    limitations: Annotated[
        str,
        StringConstraints(strict=True, min_length=1, max_length=4096, pattern=r"\S"),
    ]


class BuildProcessEvidence(BaseModel):
    """Harness-owned attribution of an agent's report, not proof of execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    attempt_id: UUID
    provenance: Literal["agent-reported"] = "agent-reported"
    report: BuildProcessReport
