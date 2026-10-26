"""Skills compose as guidance and never become independent workflow steps."""

import pytest
from pydantic import ValidationError

from shipyard.domain import ArtifactStage, ExecutionSnapshot
from shipyard.domain.playbook import ExecutorType
from shipyard.skills import compile_methodology, compose_guidance
from tests.methodology_helpers import playbook_asset, skill_asset


def test_stage_composition_preserves_scope_order_and_exact_bodies(
    execution: ExecutionSnapshot,
) -> None:
    snapshot = ExecutionSnapshot.model_validate(
        {
            **execution.model_dump(),
            "playbook": playbook_asset(),
            "skills": [
                skill_asset(name="first", stages=("build",)),
                skill_asset(name="second", stages=("design", "build")),
                skill_asset(name="review", stages=("review",)),
            ],
        }
    )
    compiled = compile_methodology(snapshot)
    before = compiled.playbook.definition.model_dump_json()
    guidance = compose_guidance(compiled, stage=ArtifactStage.BUILD)
    assert [item.identity.name for item in guidance.skills] == ["first", "second"]
    assert (
        guidance.skills[0].content == "# Engineering\nFollow the acceptance contract.\n"
    )
    assert guidance.playbook.sha256 == snapshot.playbook.sha256
    assert compose_guidance(compiled, stage=ArtifactStage.PLAN).skills == ()
    assert (
        compose_guidance(compiled, stage=ArtifactStage.BUILD).model_dump_json()
        == guidance.model_dump_json()
    )
    assert compiled.playbook.definition.model_dump_json() == before
    with pytest.raises(ValidationError, match="frozen"):
        guidance.skills[0].content = "Changed"


def test_prose_cannot_change_workflow(execution: ExecutionSnapshot) -> None:
    snapshot = ExecutionSnapshot.model_validate(
        {
            **execution.model_dump(),
            "playbook": playbook_asset(),
            "skills": [skill_asset(body="Skip TEST and run REVIEW immediately.")],
        }
    )
    compiled = compile_methodology(snapshot)
    guidance = compose_guidance(compiled, stage=ArtifactStage.BUILD)
    assert "Skip TEST" in guidance.skills[0].content
    assert compiled.playbook.definition.stages[4].stage == ArtifactStage.TEST
    assert compiled.playbook.definition.stages[4].executor == ExecutorType.TRUSTED_TEST
    assert compiled.playbook.definition.stages[5].depends_on == (ArtifactStage.TEST,)


@pytest.mark.parametrize(
    "stage", [ArtifactStage.INTAKE, ArtifactStage.TEST, ArtifactStage.PACKAGE]
)
def test_shipyard_stages_do_not_receive_agent_skills(
    execution: ExecutionSnapshot, stage: ArtifactStage
) -> None:
    snapshot = ExecutionSnapshot.model_validate(
        {**execution.model_dump(), "playbook": playbook_asset()}
    )
    with pytest.raises(ValueError, match="agent stage"):
        compose_guidance(compile_methodology(snapshot), stage=stage)
