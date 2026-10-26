"""Representative frozen execution input shared by acceptance tests."""

import hashlib
from uuid import UUID

import pytest

from shipyard.domain import (
    IntentSnapshot,
    RunContract,
    VerificationCheck,
    VerificationConfig,
    VerificationConfigSnapshot,
)
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


@pytest.fixture
def frozen_contract(execution: ExecutionSnapshot) -> RunContract:
    run_id = UUID("00000000-0000-4000-8000-000000000001")
    return RunContract(
        run_id=run_id,
        intent=IntentSnapshot.create(
            run_id=run_id, source_ref="file:/issue.md", markdown="# Request\r\n"
        ),
        base_sha="a" * 40,
        verification=VerificationConfigSnapshot(
            base_sha="a" * 40,
            source_sha256="b" * 64,
            config=VerificationConfig(
                version=1, checks=(VerificationCheck(id="tests", command="pytest"),)
            ),
        ),
        execution=execution,
    )
