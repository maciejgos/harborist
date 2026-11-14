"""Apply explicit operator disposition without rewriting historical evidence."""

import os
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from pwd import getpwuid
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
        locked = True
        try:
            stack.enter_context(execution_lock(store, run_id))
        except RunPersistenceError:
            locked = False
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
            queue.cancel_delivery(run_id)
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
            actor=getpwuid(os.getuid()).pw_name,
            timestamp=datetime.now(UTC),
            reason=request.reason,
            replacement=request.replacement,
            attempt=attempt,
            stage=record.progress.stage if record and record.progress else None,
        )
        record_retirement(root, retirement)
        if locked and store.load_state(run_id).lifecycle == "CREATED":
            store.cancel_pending(run_id)
        queue.cancel_delivery(run_id)
        return retirement


def supersede_run(
    queue: QueueStore,
    root: Path,
    run_id: UUID,
    request: RetirementRequest,
    active: QueueRecord | None,
) -> Retirement:
    from shipyard.application.context import load_context
    from shipyard.control.queue import Submission
    from shipyard.persistence.retirement import require_live_run

    replacement = request.replacement
    if replacement is None or replacement == run_id:
        raise ValueError("Supersession requires a distinct replacement Run")
    store = FileRunStore(root=root)
    store.load(replacement)
    context = load_context(
        path=store.original_directory(replacement) / "execution-context.json",
        run_id=replacement,
    )
    existing = load_retirement(root, run_id)
    if existing is None:
        require_live_run(root, replacement)
        if (
            store.selected_number(replacement)
            or store.load_state(replacement).lifecycle != "CREATED"
        ):
            raise ValueError("Replacement must be a fresh captured Run")
        if any(record.submission.run_id == replacement for record in queue.list()):
            raise ValueError("Replacement already has a service delivery")
    retirement = retire_run(queue, root, run_id, request, active)
    if not any(record.submission.run_id == replacement for record in queue.list()):
        queue.submit(
            Submission(
                run_id=replacement,
                repository=context.repository,
                runs_root=context.runs_root,
            )
        )
    return retirement
