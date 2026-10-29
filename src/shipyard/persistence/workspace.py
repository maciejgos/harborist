"""Non-contract, create-only workspace policy and admitted execution association."""

import stat
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class WorkspaceLayout(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1] = 1
    run_id: UUID
    layout: Literal["run-owned"] = "run-owned"


class WorkspaceSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1] = 1
    run_id: UUID
    attempt_id: UUID
    path: Path

    @model_validator(mode="after")
    def absolute_path(self) -> WorkspaceSelection:
        if not self.path.is_absolute():
            raise ValueError("Recorded workspace path must be absolute")
        return self


def _read_record(path: Path) -> bytes | None:
    # exists()/is_symlink() suppress access errors on Python 3.14. Only an
    # actually absent record may select legacy behavior.
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"Workspace record must not be a symlink: {path}")
    return path.read_bytes()


def load_layout(directory: Path, run_id: UUID) -> WorkspaceLayout | None:
    content = _read_record(directory / "workspace-layout.json")
    if content is None:
        return None
    layout = WorkspaceLayout.model_validate_json(content)
    if layout.run_id != run_id:
        raise ValueError("Workspace layout belongs to another Run")
    return layout


def load_selection(directory: Path, run_id: UUID) -> WorkspaceSelection | None:
    content = _read_record(directory / "execution-workspace.json")
    if content is None:
        # Honor an existing selection without rewriting it when admission records
        # the actual path and new Attempt (including an explicit override).
        content = _read_record(directory / "workspace.json")
    if content is None:
        return None
    selection = WorkspaceSelection.model_validate_json(content)
    if selection.run_id != run_id:
        raise ValueError("Workspace selection belongs to another Run")
    return selection
