"""Apply explicit operator disposition without rewriting historical evidence."""

import getpass
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from shipyard.control.queue import QueueRecord, QueueStore
from shipyard.domain.attempt import Attempt
from shipyard.persistence import FileRunStore
from shipyard.persistence.continuation import execution_lock
from shipyard.persistence.retirement import (
    Retirement,
    RetirementRequest,
    load_retirement,
    record_retirement,
)
from shipyard.persistence.run import RunPersistenceError


def retire_run(
    queue: QueueStore,
    root: Path,
    run_id: UUID,
    request: RetirementRequest,
    active: QueueRecord | None,
) -> Retirement:
    store = FileRunStore(root=root)
    with ExitStack() as stack:
        try:
            stack.enter_context(execution_lock(store, run_id))
        except RunPersistenceError:
            if active is None or active.submission.run_id != run_id:
                raise
            if store.load_state(run_id).lifecycle != "RUNNING":
                raise
        store.load(run_id)
        existing = load_retirement(root, run_id)
        if existing is not None:
            if (existing.reason, existing.replacement) != (
                request.reason,
                request.replacement,
            ):
                raise ValueError("Run already has a terminal operator disposition")
            return existing
        record = next(
            (item for item in queue.list() if item.submission.run_id == run_id), None
        )
        attempt_path = store.directory(run_id) / "attempt.json"
        attempt = (
            Attempt.model_validate_json(attempt_path.read_bytes()).attempt_id
            if attempt_path.exists()
            else None
        )
        retirement = Retirement(
            run_id=run_id,
            actor=getpass.getuser(),
            timestamp=datetime.now(UTC),
            reason=request.reason,
            replacement=request.replacement,
            attempt=attempt,
            stage=record.progress.stage if record and record.progress else None,
        )
        record_retirement(root, retirement)
        if store.load_state(run_id).lifecycle == "CREATED" and (
            active is None or active.submission.run_id != run_id
        ):
            store.cancel_pending(run_id)
        queue.cancel_delivery(run_id)
        return retirement
