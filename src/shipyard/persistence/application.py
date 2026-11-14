"""Durable create-only receipts and retryable preparation, outside packaged Runs."""

import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel

from shipyard.domain.application import ApplicationReceipt


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_record_directory(path: Path) -> None:
    if not path.exists():
        ensure_record_directory(path.parent)
        try:
            path.mkdir()
        except FileExistsError:
            pass
        _sync_directory(path.parent)
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise ValueError(
            f"Application storage must be a directory without symlinks: {path}"
        )


def _read(path: Path) -> ApplicationReceipt | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"Invalid application record: {path}")
    return ApplicationReceipt.model_validate_json(path.read_bytes())


def write_new_record(path: Path, receipt: BaseModel) -> None:
    staged = path.with_name(f".{path.name}.{uuid4()}.staged")
    try:
        with staged.open("xb") as stream:
            stream.write(receipt.model_dump_json(indent=2).encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.link(
            staged, path
        )  # Atomic create-only publication, never replace a receipt.
        _sync_directory(path.parent)
    finally:
        if staged.exists():
            staged.unlink()


class ApplicationStore:
    def __init__(
        self, *, root: Path, run_id: UUID, repository: Path, branch: str
    ) -> None:
        self.run_id = run_id
        self.repository = repository
        self.branch = branch
        key = hashlib.sha256(
            json.dumps([str(repository), f"refs/heads/{branch}"]).encode()
        ).hexdigest()
        self.directory = root / "applications" / str(run_id)
        self.path = self.directory / f"{key}.json"
        self.preparation = self.directory / f"{key}.pending.json"
        self.confirmation = self.directory / f"{key}.confirmed.json"
        self.lock = self.directory / f"{key}.lock"

    def _load(self, path: Path, candidate: str) -> ApplicationReceipt | None:
        receipt = _read(path)
        if receipt is not None and (
            receipt.run_id != self.run_id
            or receipt.repository != self.repository
            or receipt.branch != self.branch
            or receipt.candidate_sha != candidate
        ):
            raise ValueError(f"Conflicting application record: {path}")
        return receipt

    @contextmanager
    def reserve(self) -> Generator[None]:
        ensure_record_directory(self.directory)
        descriptor = os.open(self.lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"Invalid application reservation: {self.lock}")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError(
                    f"Application already active: {self.lock}; retry after it finishes"
                ) from error
            yield
        finally:
            os.close(descriptor)

    def existing(self, candidate: str) -> ApplicationReceipt | None:
        receipt = self._load(self.path, candidate)
        if receipt is not None:
            # A previous publication may have failed only at directory fsync.
            with self.path.open("rb") as stream:
                os.fsync(stream.fileno())
            _sync_directory(self.directory)
        return receipt

    def prepare(self, receipt: ApplicationReceipt) -> ApplicationReceipt:
        previous = self._load(self.preparation, receipt.candidate_sha)
        confirmed = self._load(self.confirmation, receipt.candidate_sha)
        if confirmed is not None and (
            previous is None
            or confirmed.previous_sha != previous.previous_sha
            or confirmed.operation != previous.operation
        ):
            raise ValueError(
                f"Advancement confirmation conflicts with preparation: {self.confirmation}"
            )
        # Catch an obstructed/conflicting final path before touching Git.
        self._load(self.path, receipt.candidate_sha)
        if previous is None:
            write_new_record(self.preparation, receipt)
            return receipt
        _sync_directory(self.directory)
        return previous

    def confirm(self, receipt: ApplicationReceipt) -> None:
        existing = self._load(self.confirmation, receipt.candidate_sha)
        if existing is None:
            write_new_record(self.confirmation, receipt)
        elif existing != receipt:
            raise ValueError(
                f"Conflicting advancement confirmation: {self.confirmation}"
            )

    def confirmed(self, candidate: str) -> ApplicationReceipt | None:
        return self._load(self.confirmation, candidate)

    def publish(self, receipt: ApplicationReceipt) -> None:
        write_new_record(self.path, receipt)
