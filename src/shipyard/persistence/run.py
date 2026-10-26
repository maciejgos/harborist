"""Create-only storage for a complete Phase 2 capture."""

from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter

from shipyard.domain import Run, RunContract, RunLifecycle
from shipyard.persistence.intent import FileIntentStore, IntentPersistenceError

_RUN_ID = TypeAdapter(UUID)


class RunPersistenceError(ValueError):
    """A complete Run capture could not be stored or validated."""


class RunAlreadyExistsError(RunPersistenceError):
    """A Run directory, including partial evidence, already exists."""


class FileRunStore:
    """Reserve a new directory exclusively; contract.json is published last.

    Partial writes remain inspectable. There is no automatic repair, overwrite,
    general lifecycle persistence, or multi-file/power-loss atomicity guarantee.
    """

    def __init__(self, *, root: Path) -> None:
        self._root = root

    def save(self, contract: RunContract) -> None:
        contract = RunContract.model_validate(contract.model_dump())
        directory = self._root / str(contract.run_id)
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RunPersistenceError(
                f"Cannot create Runs root {self._root}"
            ) from error
        try:
            directory.mkdir()
        except FileExistsError as error:
            raise RunAlreadyExistsError(
                f"Run path already exists: {directory}"
            ) from error
        except OSError as error:
            raise RunPersistenceError(
                f"Cannot reserve Run directory {directory}"
            ) from error
        try:
            with (directory / "run.json").open("xb") as output:
                output.write(
                    Run(run_id=contract.run_id).model_dump_json().encode("utf-8")
                )
            FileIntentStore(root=self._root).save(contract.intent)
            with (directory / "contract.json").open("xb") as output:
                output.write(contract.model_dump_json().encode("utf-8"))
        except (OSError, IntentPersistenceError) as error:
            raise RunPersistenceError(f"Cannot save Run capture {directory}") from error

    def load(self, run_id: UUID) -> RunContract:
        run_id = _RUN_ID.validate_python(run_id)
        directory = self._root / str(run_id)
        try:
            contract = RunContract.model_validate_json(
                (directory / "contract.json").read_bytes()
            )
            run = Run.model_validate_json((directory / "run.json").read_bytes())
            intent = FileIntentStore(root=self._root).load(run_id)
            if contract.run_id != run_id or run.run_id != run_id:
                raise ValueError("Persisted records must belong to requested Run")
            if run.lifecycle != RunLifecycle.CREATED:
                raise ValueError("Phase 2 capture must retain CREATED lifecycle")
            if contract.intent != intent:
                raise ValueError("Persisted intent must match frozen contract")
            return contract
        except (OSError, ValueError) as error:
            raise RunPersistenceError(f"Cannot load Run capture {directory}") from error
