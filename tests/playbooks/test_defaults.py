"""Default methodology is packaged, content-bound and independent of cwd."""

from pathlib import Path

import pytest

from shipyard.domain import ArtifactStage, ExecutionSnapshot
from shipyard.skills import compile_methodology, compose_guidance
from shipyard.skills.defaults import load_default_methodology


def test_defaults_compile_from_package_and_match_standalone_examples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, execution: ExecutionSnapshot
) -> None:
    examples = Path(__file__).resolve().parents[2] / "examples" / "intake"
    monkeypatch.chdir(tmp_path)
    playbook, skills = load_default_methodology()
    assert playbook.content.encode() == (examples / "playbook.md").read_bytes()
    assert skills[0].content.encode() == (examples / "engineering.md").read_bytes()
    snapshot = ExecutionSnapshot.model_validate(
        {**execution.model_dump(), "playbook": playbook, "skills": skills}
    )
    compiled = compile_methodology(snapshot)
    assert len(compiled.playbook.definition.stages) == 7
    for stage in (
        ArtifactStage.DESIGN,
        ArtifactStage.PLAN,
        ArtifactStage.BUILD,
        ArtifactStage.REVIEW,
    ):
        assert (
            compose_guidance(compiled, stage=stage).skills[0].identity.name
            == "engineering"
        )
