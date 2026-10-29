"""Default filesystem policy, resolved for the current user at invocation time."""

from pathlib import Path
from uuid import UUID


def data_root() -> Path:
    return Path.home() / ".shipyard"


def runs_root() -> Path:
    return data_root() / "runs"


def legacy_run_workspace(run_id: UUID) -> Path:
    return data_root() / "workspaces" / str(run_id)
