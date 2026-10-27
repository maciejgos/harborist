import hashlib
from pathlib import Path

import pytest

from shipyard.application.budget import BudgetClock
from shipyard.domain import FailureReason, Run, RunContract, RunOutcome
from shipyard.evidence.package import package_run


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
