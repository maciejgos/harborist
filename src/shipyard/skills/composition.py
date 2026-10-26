"""Compile frozen documents and select guidance, without altering topology."""

from dataclasses import dataclass

from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.execution import ExecutionSnapshot
from shipyard.domain.guidance import SkillGuidance, StageGuidance
from shipyard.domain.stage_result import AgentStage
from shipyard.playbooks import (
    PlaybookDocument,
    SkillDocument,
    parse_playbook,
    parse_skill,
)


@dataclass(frozen=True)
class CompiledMethodology:
    playbook: PlaybookDocument
    skills: tuple[SkillDocument, ...]


def compile_methodology(execution: ExecutionSnapshot) -> CompiledMethodology:
    execution = ExecutionSnapshot.model_validate(execution.model_dump())
    return CompiledMethodology(
        playbook=parse_playbook(execution.playbook),
        skills=tuple(parse_skill(asset) for asset in execution.skills),
    )


def compose_guidance(
    compiled: CompiledMethodology, *, stage: ArtifactStage
) -> StageGuidance:
    try:
        agent_stage = AgentStage(stage.value)
    except ValueError as error:
        raise ValueError("Skill composition requires a native-agent stage") from error
    return StageGuidance(
        stage=agent_stage,
        playbook=compiled.playbook.identity,
        playbook_guidance=compiled.playbook.guidance,
        skills=tuple(
            SkillGuidance(
                identity=skill.identity,
                description=skill.metadata.description,
                content=skill.guidance,
            )
            for skill in compiled.skills
            if agent_stage in skill.metadata.stages
        ),
    )
