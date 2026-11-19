from pathlib import Path

import pytest

from harborist.application.verification import execute_test
from harborist.domain import (
    RunContract,
)
from harborist.domain.attempt import Attempt
from harborist.domain.playbook_execution import StepOutcome
from harborist.git import GitRepository
from harborist.verification.config import load_verification_config
from tests.git_helpers import git, init_repository


@pytest.mark.parametrize(
    "command,outcome",
    [
        ("true", StepOutcome.SUCCEEDED),
        ("exit 2", StepOutcome.TEST_FAILED),
        ("touch residue", StepOutcome.TEST_FAILED),
    ],
)
def test_exact_candidate_frozen_checks(
    tmp_path: Path, frozen_contract: RunContract, command: str, outcome: StepOutcome
) -> None:
    workspace = tmp_path / "repo"
    init_repository(workspace)
    (workspace / "harborist.yaml").write_text(
        f'version: 1\nchecks:\n  - id: frozen\n    command: "{command}"\n'
    )
    git(workspace, "add", ".")
    git(workspace, "commit", "-m", "base")
    repository = GitRepository(path=workspace)
    base = repository.resolve_base()
    snapshot = load_verification_config(repository=repository, base_sha=base)
    contract = RunContract(
        run_id=frozen_contract.run_id,
        intent=frozen_contract.intent,
        base_sha=base,
        verification=snapshot,
        execution=frozen_contract.execution,
    )
    (workspace / "harborist.yaml").write_text("invalid candidate config")
    git(workspace, "commit", "-am", "candidate")
    attempt = Attempt.create(contract.run_id, base)
    candidate = attempt.create_candidate(repository.resolve_base())
    result = execute_test(
        contract=contract,
        attempt=attempt,
        candidate=candidate,
        workspace=workspace,
        output_dir=tmp_path / "test",
        check_timeout_seconds=2,
    )
    assert result.receipt.outcome == outcome
    assert result.receipt.candidate == candidate
    assert result.collection.checks[0].command == command
    assert (tmp_path / "test" / "manifest.json").exists()
    with pytest.raises((FileExistsError, ValueError)):
        execute_test(
            contract=contract,
            attempt=attempt,
            candidate=candidate,
            workspace=workspace,
            output_dir=tmp_path / "test",
            check_timeout_seconds=2,
        )
