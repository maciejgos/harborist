"""The single PoC workflow cannot weaken mandatory dependencies or authority."""

import json
from itertools import pairwise

import pytest
from pydantic import ValidationError

from harborist.domain import ArtifactStage
from harborist.domain.playbook import (
    ExecutorType,
    PlaybookDefinition,
    canonical_playbook,
)


def test_canonical_definition_has_fixed_authority_and_dependencies() -> None:
    playbook = canonical_playbook(version="1")
    stages = playbook.stages
    assert tuple(step.stage for step in stages) == tuple(ArtifactStage)
    assert stages[0].depends_on == ()
    assert all(
        step.depends_on == (previous.stage,) for previous, step in pairwise(stages)
    )
    assert stages[4].executor == ExecutorType.TRUSTED_TEST
    assert stages[5].read_only
    assert all(
        step.fresh_invocation
        for step in stages
        if step.executor == ExecutorType.NATIVE_AGENT
    )
    assert not stages[-1].budgeted
    serialized = playbook.model_dump_json()
    reordered = json.loads(
        serialized, object_pairs_hook=lambda pairs: dict(reversed(pairs))
    )
    assert PlaybookDefinition.model_validate(reordered).model_dump_json() == serialized
    with pytest.raises(ValidationError, match="frozen"):
        playbook.version = "2"


@pytest.mark.parametrize(
    "mutation",
    ["missing", "reordered", "repeated", "dependency", "executor", "review", "package"],
)
def test_rejects_weakened_workflow(mutation: str) -> None:
    payload = canonical_playbook(version="1").model_dump(mode="json")
    stages = payload["stages"]
    if mutation == "missing":
        del stages[4]
    elif mutation == "reordered":
        stages[1], stages[2] = stages[2], stages[1]
    elif mutation == "repeated":
        stages.insert(2, stages[1])
    elif mutation == "dependency":
        stages[5]["depends_on"] = ["build"]
    elif mutation == "executor":
        stages[4]["executor"] = "native_agent"
    elif mutation == "review":
        stages[5]["read_only"] = False
    else:
        stages[-1]["budgeted"] = True
    with pytest.raises(ValidationError, match="canonical"):
        PlaybookDefinition.model_validate(payload)
