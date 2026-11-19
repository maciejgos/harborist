"""Default filesystem policy, resolved for the current user at invocation time."""

from pathlib import Path
from uuid import UUID


def data_root() -> Path:
    current = Path.home() / ".harborist"
    previous = Path.home() / ".shipyard"
    return previous if not current.exists() and previous.is_dir() else current


def runs_root() -> Path:
    return data_root() / "runs"


def legacy_run_workspace(run_id: UUID) -> Path:
    return data_root() / "workspaces" / str(run_id)
