"""Host-side sandbox authority and bounded process execution."""

from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, TypeAdapter

from harborist.execution.cancellation import cancellation_check
from harborist.execution.process import ProcessCapture
from harborist.sandbox.host_commands import host_command

MAX_TRANSFER = 64 * 1024 * 1024
MAX_OUTPUT = 16 * 1024 * 1024
MAX_SECONDS = 3600


class HostRunner(Protocol):
    def __call__(
        self, args: tuple[str, ...], *, timeout: float, limit: int, input_bytes: bytes
    ) -> ProcessCapture: ...


class SandboxIdentity(BaseModel):
    name: str
    id: UUID
    status: str


_inventory = TypeAdapter(list[SandboxIdentity])
_ownership = TypeAdapter(dict[str, UUID | None])


class HostRuntime:
    def __init__(self, directory: Path, run: HostRunner) -> None:
        self.directory = directory
        self.run = run
        self.lock = Lock()
        self.path = directory / "ownership.json"

    def _inventory(self) -> dict[str, SandboxIdentity]:
        result = self.run(
            ("ls", "--json"), timeout=5, limit=1024 * 1024, input_bytes=b""
        )
        if result.returncode or result.timed_out or result.stdout_truncated:
            raise ValueError("Cannot establish sandbox identity")
        sandboxes = _inventory.validate_json(result.stdout)
        inventory = {sandbox.name: sandbox for sandbox in sandboxes}
        if len(sandboxes) != len(inventory):
            raise ValueError("Duplicate sandbox names")
        return inventory

    def _save(self, ownership: dict[str, UUID | None]) -> None:
        temporary = self.directory / "ownership.new"
        temporary.write_bytes(_ownership.dump_json(ownership))
        temporary.replace(self.path)

    def execute(
        self,
        args: tuple[str, ...],
        *,
        timeout: float = 10,
        limit: int = 65536,
        input_bytes: bytes = b"",
    ) -> ProcessCapture:
        if not (0 < timeout <= MAX_SECONDS and 0 < limit <= MAX_OUTPUT):
            raise ValueError("Invalid sandbox operation bounds")
        if len(input_bytes) > MAX_TRANSFER or (
            input_bytes and args[:1] not in (("exec",), ("upload",))
        ):
            raise ValueError("Invalid sandbox input")

        if args in (("version",), ("policy", "ls", "--json")):
            return self.run(args, timeout=timeout, limit=limit, input_bytes=b"")

        with self.lock:
            ownership = (
                _ownership.validate_json(self.path.read_bytes())
                if self.path.exists()
                else {}
            )
            inventory = self._inventory()
            owned = {
                name
                for name, sandbox in inventory.items()
                if name in ownership and ownership[name] == sandbox.id
            }
            if args == ("ls", "--json"):
                if any(identity is None for identity in ownership.values()):
                    raise ValueError("A sandbox creation could not be reconciled")
                output = _inventory.dump_json(
                    [inventory[name] for name in sorted(owned)]
                )
                return ProcessCapture(
                    0, False, output[:limit], b"", len(output) > limit, False
                )

            command = host_command(
                args,
                owned=owned | (set(ownership) if args[:1] == ("create",) else set()),
            )
            if command[:1] == ("create",):
                name = command[2]
                if name in inventory:
                    raise ValueError("Sandbox name is already in use")
                ownership[name] = None
                self._save(ownership)
                # Once a create starts, finish reconciling its identity even if
                # the worker disconnects, so subsequent cleanup can stop it.
                disconnected = cancellation_check.get()
                token = cancellation_check.set(None)
                try:
                    return self.run(
                        command, timeout=timeout, limit=limit, input_bytes=b""
                    )
                finally:
                    try:
                        item = self._inventory().get(name)
                        if item is not None:
                            ownership[name] = item.id
                        else:
                            ownership.pop(name)
                        self._save(ownership)
                        if (
                            item is not None
                            and disconnected is not None
                            and disconnected()
                        ):
                            self._stop_owned(item)
                    finally:
                        cancellation_check.reset(token)

        try:
            return self.run(
                command, timeout=timeout, limit=limit, input_bytes=input_bytes
            )
        except KeyboardInterrupt:
            if command[0] == "exec":
                name = command[command.index("--") + 1]
                with self.lock:
                    self._stop_owned(inventory[name])
            raise

    def _stop_owned(self, expected: SandboxIdentity) -> None:
        token = cancellation_check.set(None)
        try:
            current = self._inventory().get(expected.name)
            if (
                current is not None
                and current.id == expected.id
                and current.status != "stopped"
            ):
                result = self.run(
                    ("stop", expected.name), timeout=20, limit=65536, input_bytes=b""
                )
                if result.returncode or result.timed_out:
                    raise ValueError(
                        "Host helper could not stop the disconnected sandbox"
                    )
        finally:
            cancellation_check.reset(token)
