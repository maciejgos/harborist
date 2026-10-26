"""Agent guidance sections deliberately contain no workflow control fields."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from shipyard.domain.execution import Nonblank
from shipyard.domain.skill import MethodologyIdentity
from shipyard.domain.stage_result import AgentStage

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
