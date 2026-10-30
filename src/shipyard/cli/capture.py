"""Shared source capture preparation and copyable execution commands."""

import shlex
from pathlib import Path
from uuid import UUID

from shipyard.application import create_run
from shipyard.application.context import ExecutionContext
from shipyard.configuration import SettingsError, load_execution_settings
from shipyard.domain import ExecutionBudget, RunContract
from shipyard.git import GitRepository
from shipyard.paths import runs_root
from shipyard.persistence import FileRunStore
from shipyard.skills import compile_methodology


def capture_run(
    *,
    source: str,
    settings: Path | None,
    repo: Path,
    ref: str,
    runs_dir: Path | None,
    timeout: int,
    verification_reserve: int,
) -> tuple[RunContract, Path, Path]:
    """Share intake preparation and its single durable capture, without output."""
    repository = GitRepository(path=repo)
    root = repository.checkout_root()
    selected_settings = (
        settings if settings is not None else root / "shipyard.settings.yaml"
    )
    budget = ExecutionBudget(
        total_seconds=timeout, verification_reserve_seconds=verification_reserve
    )
    try:
        execution = load_execution_settings(path=selected_settings, budget=budget)
        compile_methodology(execution)
    except ValueError as error:
        raise SettingsError(
            f"Invalid execution settings {selected_settings}: {error}. "
            "Supply --settings PATH to select a valid file; relative explicit "
            "paths use the invocation directory."
        ) from error
    runs_dir = (runs_dir if runs_dir is not None else runs_root()).resolve()
    contract = create_run(
        source=source,
        repository=GitRepository(path=root),
        store=FileRunStore(root=runs_dir),
        execution=execution,
        ref=ref,
    )
    ExecutionContext(
        version=1, run_id=contract.run_id, repository=root, runs_root=runs_dir
    ).save()
    return contract, root, runs_dir


def execution_command(
    run_id: UUID, runs_dir: Path, workspace: Path | None = None
) -> str:
    arguments = ["shipyard", "run", str(run_id)]
    if runs_dir != runs_root().resolve():
        arguments += ["--runs-dir", str(runs_dir)]
    if workspace is not None:
        arguments += ["--workspace", str(workspace)]
    return shlex.join(arguments)
