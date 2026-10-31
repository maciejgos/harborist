"""Read-only projection; queue delivery never substitutes for validated Run state."""

from uuid import UUID

from pydantic import Field

from shipyard.control.queue import QueueRecord
from shipyard.domain import Run, RunLifecycle
from shipyard.domain.attempt import Attempt
from shipyard.persistence import FileRunStore


class RunView(QueueRecord):
    run: Run | None = None
    run_error: str | None = None
    attempt_id: UUID | None = None
    package_available: bool = False
    artifacts: dict[str, str] = Field(default_factory=dict)


def read_record(record: QueueRecord) -> RunView:
    submission = record.submission
    store = FileRunStore(root=submission.runs_root)
    directory = store.directory(submission.run_id)
    try:
        store.load(submission.run_id)
        run = store.load_state(submission.run_id)
        attempt_id: UUID | None = None
        if (directory / "attempt.json").exists():
            attempt = Attempt.model_validate_json(
                (directory / "attempt.json").read_bytes()
            )
            if attempt.run_id != submission.run_id:
                raise ValueError("Attempt identity mismatch")
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
        return RunView(
            **record.model_dump(),
            run=run,
            attempt_id=attempt_id,
            artifacts=artifacts,
            package_available=len(artifacts) == 2,
        )
    except (ValueError, OSError) as error:
        # A lifecycle snapshot and its journal can temporarily disagree during
        # finalization. Expose unavailable; never invent or repair workflow state.
        return RunView(**record.model_dump(), run_error=str(error)[:4096])
