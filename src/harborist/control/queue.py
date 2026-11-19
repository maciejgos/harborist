"""Versioned filesystem submissions; delivery state never grants verification."""

import fcntl
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harborist.domain import RunLifecycle
from harborist.domain.continuation import ContinuationRequest
from harborist.persistence import FileRunStore
from harborist.persistence.continuation import prepare_continuation
from harborist.persistence.retirement import load_retirement, require_live_run


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    run_id: UUID
    repository: Path
    runs_root: Path
    workspace: Path | None = None
    continuation: ContinuationRequest | None = None

    @field_validator("repository", "runs_root", "workspace")
    @classmethod
    def absolute_path(cls, value: Path | None) -> Path | None:
        if value is not None and (not value.is_absolute() or value.resolve() != value):
            raise ValueError("Submission paths must be absolute and resolved")
        return value


class DeliveryState(StrEnum):
    CANCELLED = "CANCELLED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class Progress(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    state: str
    reason: str | None = None


class QueueRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    submission: Submission
    state: DeliveryState = DeliveryState.QUEUED
    submitted_at: datetime
    updated_at: datetime
    stages: dict[str, Progress] = Field(default_factory=dict)
    progress: Progress | None = None
    error: str | None = None


class QueueStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory = self.root / "queue"
        self.directory.mkdir(mode=0o700, exist_ok=True)

    @contextmanager
    def _locked(self) -> Generator[None]:
        with (self.root / "queue.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _path(self, run_id: UUID) -> Path:
        return self.directory / f"{run_id}.json"

    def _read(self, run_id: UUID) -> QueueRecord:
        try:
            record = QueueRecord.model_validate_json(self._path(run_id).read_bytes())
            if record.submission.run_id != run_id:
                raise ValueError("Queue identity mismatch")
            return record
        except (OSError, ValueError) as error:
            raise ValueError(f"Cannot read submission {run_id}: {error}") from error

    def _write(self, record: QueueRecord) -> None:
        # Readers and writers share the lock. fsync before publishing the snapshot.
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(dir=self.directory, delete=False) as output:
                temporary = Path(output.name)
                output.write(record.model_dump_json().encode())
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self._path(record.submission.run_id))
            descriptor = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _records(self) -> list[QueueRecord]:
        return sorted(
            (self._read(UUID(path.stem)) for path in self.directory.glob("*.json")),
            key=lambda record: (record.submitted_at, str(record.submission.run_id)),
        )

    def _archive_path(self, submission: Submission) -> Path:
        key = (
            str(submission.continuation.request_id)
            if submission.continuation
            else "initial"
        )
        return self.root / "deliveries" / str(submission.run_id) / f"{key}.json"

    def submit(self, submission: Submission) -> QueueRecord:
        with self._locked():
            require_live_run(submission.runs_root, submission.run_id)
            existing = (
                self._read(submission.run_id)
                if self._path(submission.run_id).exists()
                else None
            )
            if existing is not None and existing.submission == submission:
                return existing
            if existing is not None and (
                existing.submission.repository != submission.repository
                or existing.submission.runs_root != submission.runs_root
            ):
                raise ValueError("Conflicting repository or Runs root for existing Run")
            archived = self._archive_path(submission)
            if archived.exists():
                record = QueueRecord.model_validate_json(archived.read_bytes())
                if record.submission != submission:
                    raise ValueError("Conflicting archived submission")
                return record
            if existing is not None and (
                submission.continuation is None
                or existing.state in {DeliveryState.QUEUED, DeliveryState.RUNNING}
            ):
                raise ValueError("Conflicting submission for existing Run")
            store = FileRunStore(root=submission.runs_root)
            store.load(submission.run_id)
            if submission.continuation is not None:
                prepare_continuation(
                    store=store,
                    run_id=submission.run_id,
                    request=submission.continuation,
                    dry_run=True,
                )
            elif store.load_state(submission.run_id).lifecycle != RunLifecycle.CREATED:
                raise ValueError("New submissions require a CREATED Run")
            if existing is not None:
                archive = self._archive_path(existing.submission)
                archive.parent.mkdir(parents=True, exist_ok=True)
                if archive.exists():
                    if (
                        QueueRecord.model_validate_json(archive.read_bytes())
                        != existing
                    ):
                        raise ValueError("Conflicting retained delivery history")
                else:
                    with archive.open("xb") as output:
                        output.write(existing.model_dump_json().encode())
                        output.flush()
                        os.fsync(output.fileno())
            now = datetime.now(UTC)
            record = QueueRecord(
                submission=submission, submitted_at=now, updated_at=now
            )
            self._write(record)
            return record

    def get(self, run_id: UUID) -> QueueRecord:
        with self._locked():
            return self._read(run_id)

    def list(self) -> list[QueueRecord]:
        with self._locked():
            return self._records()

    def claim(self) -> QueueRecord | None:
        with self._locked():
            records = self._records()
            if any(item.state == DeliveryState.RUNNING for item in records):
                return None
            for record in records:
                if record.state == DeliveryState.QUEUED:
                    if load_retirement(
                        record.submission.runs_root, record.submission.run_id
                    ):
                        self._change(record, state=DeliveryState.CANCELLED)
                        continue
                    return self._change(record, state=DeliveryState.RUNNING)
            return None

    def _change(self, record: QueueRecord, **changes: object) -> QueueRecord:
        updated = QueueRecord.model_validate(
            {**record.model_dump(), **changes, "updated_at": datetime.now(UTC)}
        )
        self._write(updated)
        return updated

    def update_progress(self, run_id: UUID, progress: Progress) -> None:
        with self._locked():
            record = self._read(run_id)
            if record.state != DeliveryState.RUNNING:
                raise ValueError("Progress requires an active claim")
            self._change(
                record,
                progress=progress,
                stages={**record.stages, progress.stage: progress},
            )

    def finish(
        self, run_id: UUID, *, error: str | None = None, cancelled: bool = False
    ) -> QueueRecord:
        with self._locked():
            record = self._read(run_id)
            if record.state != DeliveryState.RUNNING:
                raise ValueError("Completion requires an active claim")
            return self._change(
                record,
                state=DeliveryState.CANCELLED
                if cancelled
                else (
                    DeliveryState.FAILED
                    if error is not None
                    else DeliveryState.FINISHED
                ),
                error=error[:4096] if error is not None else None,
            )

    def cancel_delivery(self, run_id: UUID) -> None:
        with self._locked():
            if self._path(run_id).exists():
                record = self._read(run_id)
                if record.state == DeliveryState.QUEUED:
                    self._change(record, state=DeliveryState.CANCELLED)

    def interrupt_claims(self) -> None:
        """Only the exclusive service owner may call this on startup."""
        with self._locked():
            for record in self._records():
                if record.state == DeliveryState.RUNNING:
                    if load_retirement(
                        record.submission.runs_root, record.submission.run_id
                    ):
                        self._change(record, state=DeliveryState.CANCELLED)
                        continue
                    self._change(
                        record,
                        state=DeliveryState.INTERRUPTED,
                        error="Service ownership lost; inspect retained evidence; no automatic retry",
                    )
