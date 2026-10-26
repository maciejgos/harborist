"""Representative frozen execution input shared by acceptance tests."""

import hashlib

import pytest

from shipyard.domain.execution import (
    AgentProfile,
    ExecutionBudget,
    ExecutionSnapshot,
    MethodologyAsset,
)


@pytest.fixture
def execution() -> ExecutionSnapshot:
    content = "# Playbook\nINTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE\n"
    return ExecutionSnapshot(
        playbook=MethodologyAsset(
            name="bounded-repository-change",
            version="1",
            content=content,
            sha256=hashlib.sha256(content.encode()).hexdigest(),
        ),
        skills=(),
        agent_profile=AgentProfile(
            name="test-agent",
            version="1",
            provider="codex",
            model="test-model",
            arguments=(),
        ),
        sandbox_policy="trusted-local",
        budget=ExecutionBudget(total_seconds=1800, verification_reserve_seconds=300),
    )
