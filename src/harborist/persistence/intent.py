"""Intent files and metadata, separate from full Run persistence."""

from os.path import lexists
from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from harborist.domain import ArtifactReference, IntentSnapshot


class IntentPersistenceError(ValueError):
    """Intent files could not be saved or validated on load."""


class IntentAlreadyExistsError(IntentPersistenceError):
    """A save would replace an existing or incomplete intent capture."""


class _IntentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: Annotated[str, StringConstraints(strict=True, min_length=1)]
    source_url: str | None = Field(default=None, exclude_if=lambda url: url is None)
    artifact: ArtifactReference


_RUN_ID_ADAPTER = TypeAdapter(UUID)


class FileIntentStore:
    """Persist intent under an explicit Runs root without advancing domain state."""

    def __init__(self, *, root: Path, directory: Path | None = None) -> None:
        self._root = root
        self._directory = directory

    def save(self, snapshot: IntentSnapshot) -> None:
        snapshot = IntentSnapshot.model_validate(snapshot.model_dump())
        metadata = _IntentMetadata(
            source_ref=snapshot.source_ref,
            source_url=snapshot.source_url,
            artifact=snapshot.artifact,
        )
        directory = self._directory or self._root / str(snapshot.run_id)
        files = (
            (directory / "intent.md", snapshot.markdown.encode("utf-8")),
            (
                directory / "intent.json",
                metadata.model_dump_json(indent=2).encode("utf-8"),
            ),
        )
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise IntentPersistenceError(
                f"Cannot save intent under {directory}"
            ) from error
        for path, _ in files:
            if lexists(path):
                raise IntentAlreadyExistsError(
                    f"Cannot save intent: path already exists: {path}"
                )
        for path, content in files:
            try:
                with path.open("xb") as output:
                    output.write(content)
            except FileExistsError as error:
                raise IntentAlreadyExistsError(
                    f"Cannot save intent: path already exists: {path}"
                ) from error
            except OSError as error:
                raise IntentPersistenceError(f"Cannot save intent to {path}") from error

    def load(self, run_id: UUID) -> IntentSnapshot:
        run_id = _RUN_ID_ADAPTER.validate_python(run_id)
        directory = self._directory or self._root / str(run_id)
        path = directory / "intent.json"
        try:
            metadata = _IntentMetadata.model_validate_json(path.read_bytes())
            path = directory / "intent.md"
            snapshot = IntentSnapshot(
                source_ref=metadata.source_ref,
                source_url=metadata.source_url,
                artifact=metadata.artifact,
                markdown=path.read_bytes().decode("utf-8"),
            )
            if snapshot.run_id != run_id:
                raise ValueError("Persisted intent belongs to a different Run")
        except (OSError, ValueError) as error:
            raise IntentPersistenceError(f"Cannot load intent from {path}") from error
        return snapshot
