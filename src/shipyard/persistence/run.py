"""Frozen captures and exclusive synchronous lifecycle persistence."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter

from shipyard.domain import Run, RunContract, RunLifecycle
from shipyard.domain.event import RunEvent, RunEventType
from shipyard.persistence.intent import FileIntentStore, IntentPersistenceError
from shipyard.persistence.workspace import WorkspaceLayout, load_layout

_RUN_ID = TypeAdapter(UUID)


class RunPersistenceError(ValueError):
    """A complete Run capture could not be stored or validated."""


class RunAlreadyExistsError(RunPersistenceError):
    """A Run directory, including partial evidence, already exists."""


class FileRunStore:
    """Reserve a new directory exclusively; contract.json is published last.

    Partial writes remain inspectable. There is no automatic repair, overwrite,
    recovery, or multi-file/power-loss atomicity guarantee.
    """

    def __init__(self, *, root: Path, attempt_number: int | None = None) -> None:
        self._root = root
        self.attempt_number = attempt_number

    def save(self, contract: RunContract) -> None:
        contract = RunContract.model_validate(contract.model_dump())
        directory = self.directory(contract.run_id)
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise RunPersistenceError(
                f"Cannot create Runs root {self._root}: {error}; "
                "check directory access and obstructing files or choose --runs-dir"
            ) from error
        try:
            directory.parent.mkdir(parents=True, exist_ok=True)
            directory.mkdir()
        except FileExistsError as error:
            raise RunAlreadyExistsError(
                f"Run path already exists: {directory}"
            ) from error
        except OSError as error:
            raise RunPersistenceError(
                f"Cannot reserve Run directory {directory}: {error}; "
                "check directory access or choose --runs-dir"
            ) from error
        try:
            with (directory / "run.json").open("xb") as output:
                output.write(
                    Run(run_id=contract.run_id).model_dump_json().encode("utf-8")
                )
            FileIntentStore(root=self._root, directory=directory).save(contract.intent)
            with (directory / "workspace-layout.json").open("xb") as output:
                output.write(
                    WorkspaceLayout(run_id=contract.run_id)
                    .model_dump_json()
                    .encode("utf-8")
                )
            with (directory / "contract.json").open("xb") as output:
                output.write(contract.model_dump_json().encode("utf-8"))
        except (OSError, IntentPersistenceError) as error:
            raise RunPersistenceError(
                f"Cannot save Run capture {directory}: {error}; check directory access "
                "or choose --runs-dir; partial capture is retained"
            ) from error

    def load(self, run_id: UUID) -> RunContract:
        run_id = _RUN_ID.validate_python(run_id)
        directory = self.directory(run_id)
        try:
            contract = RunContract.model_validate_json(
                (directory / "contract.json").read_bytes()
            )
            run = Run.model_validate_json((directory / "run.json").read_bytes())
            intent = FileIntentStore(root=self._root, directory=directory).load(run_id)
            if contract.run_id != run_id or run.run_id != run_id:
                raise ValueError("Persisted records must belong to requested Run")
            load_layout(directory, run_id)
            self.load_state(run_id)
            if self.selected_number(run_id) != 0:
                from shipyard.persistence.continuation import load_continuation

                record = load_continuation(self, run_id)
                attempt_path = directory / "attempt.json"
                if attempt_path.exists():
                    from shipyard.domain.attempt import Attempt

                    if (
                        Attempt.model_validate_json(attempt_path.read_bytes())
                        != record.attempt
                    ):
                        raise ValueError("Attempt differs from explicit admission")
                if (
                    run.verification is not None
                    and run.verification.attempt != record.attempt
                ):
                    raise ValueError("Verification belongs to another Attempt")
                if contract != self.pinned(run_id, 0).load(run_id):
                    raise ValueError("Continuation changed the frozen contract")
            if run.verification is not None and (
                run.verification.verification != contract.verification
                or run.verification.attempt.start_sha
                != self.attempt_start(run_id, contract.base_sha)
            ):
                raise ValueError("Verification must match frozen contract")
            if contract.intent != intent:
                raise ValueError("Persisted intent must match frozen contract")
            return contract
        except (OSError, ValueError) as error:
            raise RunPersistenceError(
                f"Cannot load Run capture {directory}: {error}; "
                "check the Run ID, --runs-dir and directory access"
            ) from error

    def original_directory(self, run_id: UUID) -> Path:
        return self._root / str(_RUN_ID.validate_python(run_id))

    def numbers(self, run_id: UUID) -> list[int]:
        parent = self.original_directory(run_id) / "attempts"
        if parent.is_symlink():
            raise RunPersistenceError("Attempts directory must not be a symlink")
        if not parent.exists():
            return [0]
        numbers: list[int] = []
        for entry in parent.iterdir():
            if entry.is_symlink() or not entry.is_dir() or not entry.name.isdigit():
                raise RunPersistenceError("Invalid attempt directory")
            number = int(entry.name)
            if number < 1 or entry.name != f"{number:06d}":
                raise RunPersistenceError("Invalid attempt number")
            numbers.append(number)
        numbers.sort()
        if numbers != list(range(1, len(numbers) + 1)):
            raise RunPersistenceError("Attempt history has gaps")
        return [0, *numbers]

    def selected_number(self, run_id: UUID) -> int:
        return (
            self.attempt_number
            if self.attempt_number is not None
            else self.numbers(run_id)[-1]
        )

    def pinned(self, run_id: UUID, number: int | None = None) -> FileRunStore:
        return FileRunStore(
            root=self._root,
            attempt_number=self.selected_number(run_id) if number is None else number,
        )

    def directory(self, run_id: UUID) -> Path:
        original = self.original_directory(run_id)
        number = self.selected_number(run_id)
        return original if number == 0 else original / "attempts" / f"{number:06d}"

    def attempt_start(self, run_id: UUID, base: str) -> str:
        if self.selected_number(run_id) == 0:
            return base
        from shipyard.persistence.continuation import load_continuation

        return load_continuation(self, run_id).attempt.start_sha

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
            raise RunPersistenceError(
                f"Cannot load Run lifecycle {directory}: {error}; "
                "check the Run ID, --runs-dir and directory access"
            ) from error

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
            raise RunPersistenceError(
                f"Cannot reserve Run execution {directory}: {error}; "
                "check directory access and retained execution records"
            ) from error
        return state.start()

    def finish(self, run: Run) -> None:
        contract = self.load(run.run_id)
        if run.verification is not None and (
            run.verification.verification != contract.verification
            or run.verification.attempt.start_sha
            != self.attempt_start(run.run_id, contract.base_sha)
        ):
            raise RunPersistenceError("Verification must match the frozen contract")
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
