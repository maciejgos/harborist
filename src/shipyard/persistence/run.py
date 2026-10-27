"""Frozen captures and exclusive synchronous lifecycle persistence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter

from shipyard.domain import Run, RunContract, RunLifecycle
from shipyard.domain.event import RunEvent, RunEventType
from shipyard.persistence.intent import FileIntentStore, IntentPersistenceError

_RUN_ID = TypeAdapter(UUID)


class RunPersistenceError(ValueError):
    """A complete Run capture could not be stored or validated."""


class RunAlreadyExistsError(RunPersistenceError):
    """A Run directory, including partial evidence, already exists."""


class FileRunStore:
    """Reserve a new directory exclusively; contract.json is published last.

    Partial writes remain inspectable. There is no automatic repair, overwrite,
    automatic recovery, or multi-file/power-loss atomicity guarantee.
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
            self.load_state(run_id)
            if contract.intent != intent:
                raise ValueError("Persisted intent must match frozen contract")
            return contract
        except (OSError, ValueError) as error:
            raise RunPersistenceError(f"Cannot load Run capture {directory}") from error

    def directory(self, run_id: UUID) -> Path:
        return self._root / str(_RUN_ID.validate_python(run_id))

    def load_state(self, run_id: UUID) -> Run:
        directory = self.directory(run_id)
        try:
            run = Run.model_validate_json((directory / "run.json").read_bytes())
            if run.run_id != run_id:
                raise ValueError("Run identity mismatch")
            journal = directory / "events.jsonl"
            if journal.exists():
                events = [
                    RunEvent.model_validate_json(line)
                    for line in journal.read_bytes().splitlines()
                ]
                previous = Run(run_id=run_id)
                for index, event in enumerate(events):
                    if event.run_id != run_id:
                        raise ValueError("Foreign lifecycle event")
                    if index == 0:
                        expected = previous
                    elif event.event_type == RunEventType.RUN_STARTED:
                        expected = previous.start()
                    elif event.event_type == RunEventType.RUN_COMPLETED:
                        assert event.run.outcome is not None
                        expected = previous.complete(
                            event.run.outcome, verification=event.run.verification
                        )
                    elif event.event_type == RunEventType.RUN_FAILED:
                        assert event.run.failure_reason is not None
                        expected = previous.fail(event.run.failure_reason)
                    elif event.event_type == RunEventType.RUN_CANCELLED:
                        expected = previous.cancel()
                    else:
                        raise ValueError("Invalid lifecycle event order")
                    if expected != event.run:
                        raise ValueError("Lifecycle journal transition mismatch")
                    previous = event.run
                if (
                    not events
                    or events[0].event_type != RunEventType.RUN_CREATED
                    or previous != run
                ):
                    raise ValueError("Run snapshot disagrees with lifecycle journal")
            elif run.lifecycle != RunLifecycle.CREATED:
                raise ValueError("Non-CREATED state requires lifecycle journal")
            return run
        except (OSError, ValueError) as error:
            raise RunPersistenceError("Cannot load Run lifecycle") from error

    def begin(self, run_id: UUID) -> Run:
        """Exclusively admit one synchronous attempt; partial admissions block retry."""
        self.load(run_id)
        state = self.load_state(run_id)
        if state.lifecycle != RunLifecycle.CREATED:
            raise RunPersistenceError("Execution requires a CREATED Run")
        directory = self.directory(run_id)
        try:
            (directory / ".execution").mkdir()
            with (directory / "events.jsonl").open("x", encoding="utf-8") as output:
                output.write(
                    RunEvent.create(
                        event_type=RunEventType.RUN_CREATED,
                        run=state,
                        occurred_at=datetime.now(UTC),
                    ).model_dump_json()
                    + "\n"
                )
            self._write_transition(state.start(), RunEventType.RUN_STARTED)
        except OSError as error:
            raise RunPersistenceError("Cannot reserve Run execution") from error
        return state.start()

    def finish(self, run: Run) -> None:
        previous = self.load_state(run.run_id)
        if previous.lifecycle != RunLifecycle.RUNNING:
            raise RunPersistenceError("Only an active execution may finalize")
        event_type = {
            RunLifecycle.COMPLETED: RunEventType.RUN_COMPLETED,
            RunLifecycle.FAILED: RunEventType.RUN_FAILED,
            RunLifecycle.CANCELLED: RunEventType.RUN_CANCELLED,
        }.get(run.lifecycle)
        if event_type is None:
            raise RunPersistenceError("Finalization requires a terminal Run")
        self._write_transition(run, event_type)

    def _write_transition(self, run: Run, event_type: RunEventType) -> None:
        directory = self.directory(run.run_id)
        event = RunEvent.create(
            event_type=event_type, run=run, occurred_at=datetime.now(UTC)
        )
        with (directory / "events.jsonl").open("a", encoding="utf-8") as output:
            output.write(event.model_dump_json() + "\n")
        temporary = directory / ".run-next.json"
        with temporary.open("x", encoding="utf-8") as output:
            output.write(run.model_dump_json())
        temporary.replace(directory / "run.json")
