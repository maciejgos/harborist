"""Agent guidance sections deliberately contain no workflow control fields."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from harborist.domain.execution import Nonblank
from harborist.domain.skill import MethodologyIdentity
from harborist.domain.stage_result import AgentStage

type _Text = Annotated[str, StringConstraints(strict=True)]


class SkillGuidance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: MethodologyIdentity
    description: Nonblank
    content: _Text


class StageGuidance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: AgentStage
    playbook: MethodologyIdentity
    playbook_guidance: _Text
    skills: tuple[SkillGuidance, ...]
