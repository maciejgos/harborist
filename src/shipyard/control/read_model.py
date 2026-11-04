"""Read-only projection; queue delivery never substitutes for validated Run state."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shipyard.control.queue import DeliveryState, Progress, QueueRecord, Submission
from shipyard.control.stage_history import read_stage_history
from shipyard.domain import Run, RunLifecycle
from shipyard.domain.attempt import Attempt
from shipyard.persistence import FileRunStore
from shipyard.persistence.continuation import load_continuation


class SavedRunLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    runs_root: Path


class RunView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    submission: Submission | SavedRunLocation
    source: Literal["service", "saved"] = "service"
    state: DeliveryState | None = None
    submitted_at: datetime | None = None
    recorded_at: datetime | None = None
    updated_at: datetime | None = None
    stages: dict[str, Progress] = Field(default_factory=dict)
    stage_errors: dict[str, str] = Field(default_factory=dict)
    progress: Progress | None = None
    error: str | None = None
    title: str = ""
    candidate_sha: str | None = None
    run: Run | None = None
    run_error: str | None = None
    attempt_id: UUID | None = None
    attempt_number: int = 0
    package_available: bool = False
    artifacts: dict[str, str] = Field(default_factory=dict)


def read_record(record: QueueRecord) -> RunView:
    return _project(RunView.model_validate(record.model_dump()))


def read_saved(root: Path, run_id: UUID) -> RunView:
    try:
        directory = FileRunStore(root=root).directory(run_id)
    except ValueError, OSError:
        return _project(
            RunView(
                submission=SavedRunLocation(run_id=run_id, runs_root=root),
                source="saved",
            )
        )
    timestamps: dict[str, datetime] = {}
    for field, name in (("recorded_at", "contract.json"), ("updated_at", "run.json")):
        try:
            timestamps[field] = datetime.fromtimestamp(
                (directory / name).stat().st_mtime, UTC
            )
        except OSError:
            pass
    return _project(
        RunView(
            submission=SavedRunLocation(run_id=run_id, runs_root=root),
            source="saved",
            recorded_at=timestamps.get("recorded_at"),
            updated_at=timestamps.get("updated_at"),
        )
    )


def _project(view: RunView) -> RunView:
    submission = view.submission
    store = FileRunStore(root=submission.runs_root)
    try:
        store = store.pinned(submission.run_id)
        directory = store.directory(submission.run_id)
        contract = store.load(submission.run_id)
        run = store.load_state(submission.run_id)
        attempt_id: UUID | None = None
        attempt: Attempt | None = None
        if (directory / "attempt.json").exists():
            attempt = Attempt.model_validate_json(
                (directory / "attempt.json").read_bytes()
            )
            if (
                attempt.run_id != submission.run_id
                or attempt.start_sha
                != store.attempt_start(submission.run_id, contract.base_sha)
            ):
                raise ValueError("Attempt identity mismatch")
            if run.verification is not None and run.verification.attempt != attempt:
                raise ValueError("Attempt differs from terminal verification")
            attempt_id = attempt.attempt_id
        terminal = run.lifecycle in (
            RunLifecycle.COMPLETED,
            RunLifecycle.FAILED,
            RunLifecycle.CANCELLED,
        )
        artifacts = {
            name: str(directory / name)
            for name in ("report.md", "evidence.json")
            if terminal and (directory / name).is_file()
        }
        history = (
            read_stage_history(
                directory=directory, contract=contract, run=run, attempt=attempt
            )
            if attempt is not None
            else None
        )
        number = store.selected_number(submission.run_id)
        observations = view.stages
        progress = view.progress
        if number and (
            not isinstance(submission, Submission)
            or submission.continuation is None
            or submission.continuation.request_id
            != load_continuation(store, submission.run_id).request.request_id
        ):
            observations = {}
            progress = None
        return RunView.model_validate(
            {
                **view.model_dump(),
                "attempt_number": number,
                "progress": progress,
                "stages": {**(history.stages if history else {}), **observations},
                "stage_errors": history.errors if history else {},
                "run": run,
                "title": next(
                    (
                        line.strip().lstrip("# ")[:200]
                        for line in contract.intent.markdown.splitlines()
                        if line.strip()
                    ),
                    "Untitled request",
                ),
                "candidate_sha": run.verification.candidate.candidate_sha
                if run.verification
                else None,
                "attempt_id": attempt_id,
                "artifacts": artifacts,
                "package_available": len(artifacts) == 2,
            }
        )
    except (ValueError, OSError) as error:
        # A lifecycle snapshot and its journal can temporarily disagree during
        # finalization. Expose unavailable; never invent or repair workflow state.
        return RunView.model_validate(
            {**view.model_dump(), "run_error": str(error)[:4096]}
        )
