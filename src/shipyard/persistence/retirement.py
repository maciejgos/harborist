"""Immutable Run-level operator disposition beside historical Attempts."""

from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shipyard.persistence.application import ensure_record_directory, write_new_record


class RetirementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=1000)
    replacement: UUID | None = None
    runs_root: Path | None = None


class Retirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    actor: str
    timestamp: datetime
    reason: str
    replacement: UUID | None
    attempt: UUID | None
    stage: str | None


def retirement_path(root: Path, run_id: UUID) -> Path:
    return root / "retirements" / f"{run_id}.json"


def load_retirement(root: Path, run_id: UUID) -> Retirement | None:
    try:
        record = Retirement.model_validate_json(
            retirement_path(root, run_id).read_bytes()
        )
    except FileNotFoundError:
        return None
    if record.run_id != run_id:
        raise ValueError("Invalid Run retirement identity")
    return record


def record_retirement(root: Path, record: Retirement) -> None:
    path = retirement_path(root, record.run_id)
    ensure_record_directory(path.parent)
    write_new_record(path, record)


def require_live_run(root: Path, run_id: UUID) -> None:
    if load_retirement(root, run_id) is not None:
        raise ValueError("Run is terminal after cancellation or supersession")
