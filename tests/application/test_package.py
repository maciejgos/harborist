import hashlib
from pathlib import Path

import pytest

from harborist.application.budget import BudgetClock
from harborist.domain import FailureReason, Run, RunContract, RunOutcome
from harborist.evidence.package import package_run


@pytest.mark.parametrize(
    "terminal",
    [
        "NEEDS_CLARIFICATION",
        "NEEDS_RESCOPING",
        "TEST_FAILED",
        "CHANGES_REQUIRED",
        "FAILED",
        "CANCELLED",
    ],
)
def test_package_terminal_outcomes_without_admission(
    tmp_path: Path,
    frozen_contract: RunContract,
    terminal: str,
) -> None:
    run = Run(run_id=frozen_contract.run_id).start()
    if terminal == "FAILED":
        run = run.fail(FailureReason.TIME_BUDGET_EXCEEDED)
    elif terminal == "CANCELLED":
        run = run.cancel()
    else:
        run = run.complete(RunOutcome(terminal))
    (tmp_path / "intent.md").write_text(frozen_contract.intent.markdown)
    clock = BudgetClock(frozen_contract.execution.budget)
    evidence = package_run(
        directory=tmp_path,
        contract=frozen_contract,
        run=run,
        timing=clock.timing(None),
    )
    assert terminal in (tmp_path / "report.md").read_text()
    assert evidence.run == run
    indexed = next(item for item in evidence.files if item.path == "intent.md")
    assert (
        indexed.sha256
        == hashlib.sha256((tmp_path / "intent.md").read_bytes()).hexdigest()
    )
    assert "UNKNOWN" in (tmp_path / "report.md").read_text()
    assert "candidate" in " ".join(evidence.unverified).lower()
    before = (tmp_path / "evidence.json").read_bytes()
    with pytest.raises(FileExistsError):
        package_run(
            directory=tmp_path,
            contract=frozen_contract,
            run=run,
            timing=clock.timing(None),
        )
    assert (tmp_path / "evidence.json").read_bytes() == before


def test_package_rejects_nonterminal_and_symlinks(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    clock = BudgetClock(frozen_contract.execution.budget)
    with pytest.raises(ValueError, match="terminal"):
        package_run(
            directory=tmp_path,
            contract=frozen_contract,
            run=Run(run_id=frozen_contract.run_id),
            timing=clock.timing(None),
        )
    (tmp_path / "unsafe").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError, match="symlink"):
        package_run(
            directory=tmp_path,
            contract=frozen_contract,
            run=Run(run_id=frozen_contract.run_id).cancel(),
            timing=clock.timing(None),
        )


def test_package_prunes_only_validated_workspace_and_retains_evidence_validation(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from harborist.persistence.workspace import WorkspaceLayout

    (tmp_path / "workspace-layout.json").write_text(
        WorkspaceLayout(run_id=frozen_contract.run_id).model_dump_json()
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file").write_text("mutable checkout")
    (workspace / "link").symlink_to("missing")
    clock = BudgetClock(frozen_contract.execution.budget)
    # Evidence outside the checkout remains strictly validated before PACKAGE.
    outside = tmp_path / "unsafe"
    outside.symlink_to(workspace / "file")
    with pytest.raises(ValueError, match="symlink"):
        package_run(
            directory=tmp_path,
            contract=frozen_contract,
            run=Run(run_id=frozen_contract.run_id).cancel(),
            timing=clock.timing(None),
            workspace=workspace,
        )
    assert not (tmp_path / ".package").exists()
    outside.unlink()
    evidence = package_run(
        directory=tmp_path,
        contract=frozen_contract,
        run=Run(run_id=frozen_contract.run_id).cancel(),
        timing=clock.timing(None),
        workspace=workspace,
    )
    assert evidence.workspace == workspace.resolve()
    assert not any(f.path.startswith("workspace/") for f in evidence.files)


def test_package_rejects_workspace_root_symlink(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from harborist.persistence.workspace import WorkspaceLayout

    (tmp_path / "workspace-layout.json").write_text(
        WorkspaceLayout(run_id=frozen_contract.run_id).model_dump_json()
    )
    workspace = tmp_path / "workspace"
    workspace.symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError):
        package_run(
            directory=tmp_path,
            contract=frozen_contract,
            run=Run(run_id=frozen_contract.run_id).cancel(),
            timing=BudgetClock(frozen_contract.execution.budget).timing(None),
            workspace=workspace,
        )
    assert not (tmp_path / ".package").exists()
