"""Read-only discovery of saved captures plus service delivery metadata."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from harborist.control.queue import QueueStore
from harborist.control.read_model import RunView, read_record, read_saved


class RunHistory:
    def __init__(self, queue: QueueStore, *, root: Path) -> None:
        self.queue = queue
        self.root = root.resolve()

    def _saved_ids(self) -> set[UUID]:
        try:
            entries = list(self.root.iterdir())
        except FileNotFoundError:
            return set()
        result: set[UUID] = set()
        for entry in entries:
            if entry.is_symlink() or not entry.is_dir():
                continue
            try:
                run_id = UUID(entry.name)
            except ValueError:
                continue
            if entry.name == str(run_id):
                result.add(run_id)
        return result

    def list(self) -> list[RunView]:
        queued = {record.submission.run_id: record for record in self.queue.list()}
        saved = self._saved_ids()
        for run_id in saved & queued.keys():
            if queued[run_id].submission.runs_root != self.root:
                raise ValueError(
                    f"Run {run_id} appears in multiple Runs roots; cannot mix history or evidence"
                )
        views = [read_record(record) for record in queued.values()]
        views.extend(read_saved(self.root, run_id) for run_id in saved - queued.keys())
        return sorted(
            views,
            key=lambda view: (
                view.submitted_at
                or view.recorded_at
                or datetime.min.replace(tzinfo=UTC),
                str(view.submission.run_id),
            ),
        )

    def get(self, run_id: UUID) -> RunView:
        for view in self.list():
            if view.submission.run_id == run_id:
                return view
        raise ValueError(f"Unknown Run {run_id}")
