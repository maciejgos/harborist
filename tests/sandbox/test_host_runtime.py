import json
from pathlib import Path

import pytest

from harborist.domain.sandbox import CODEX_KIT
from harborist.execution.process import ProcessCapture
from harborist.sandbox.host_runtime import HostRuntime

NAME = "harborist-build-0123456789abcdef"
CREATE = (
    "create",
    "--name",
    NAME,
    "--cpus",
    "2",
    "--memory",
    "2048m",
    "--skills",
    "off",
    "--static-mcp",
    "none",
    CODEX_KIT,
)


class FakeSandboxes:
    def __init__(self) -> None:
        self.inventory: dict[str, str] = {}
        self.calls: list[tuple[str, ...]] = []

    def run(
        self, args: tuple[str, ...], *, timeout: float, limit: int, input_bytes: bytes
    ) -> ProcessCapture:
        self.calls.append(args)
        output = b""
        match args:
            case ("ls", "--json"):
                output = json.dumps(
                    [
                        {"name": name, "id": identity, "status": "running"}
                        for name, identity in self.inventory.items()
                    ]
                ).encode()
            case ("create", *_):
                self.inventory[NAME] = "01234567-89ab-cdef-0123-456789abcdef"
            case _:
                pass
        return ProcessCapture(0, False, output, b"", False, False)


def test_persisted_ownership_rejects_a_reused_name(tmp_path: Path) -> None:
    backend = FakeSandboxes()
    HostRuntime(tmp_path, backend.run).execute(CREATE)
    restarted = HostRuntime(tmp_path, backend.run)
    restarted.execute(("stop", NAME))
    assert backend.calls[-1] == ("stop", NAME)
    backend.inventory[NAME] = "fedcba98-7654-3210-fedc-ba9876543210"
    with pytest.raises(ValueError):
        restarted.execute(("rm", "--force", NAME))
    assert ("rm", "--force", NAME) not in backend.calls
    assert json.loads(restarted.execute(("ls", "--json")).stdout) == []


def test_an_existing_name_cannot_be_claimed(tmp_path: Path) -> None:
    backend = FakeSandboxes()
    backend.inventory[NAME] = "01234567-89ab-cdef-0123-456789abcdef"
    with pytest.raises(ValueError):
        HostRuntime(tmp_path, backend.run).execute(CREATE)
    assert CREATE not in backend.calls


def test_disconnected_guest_execution_stops_owned_vm(tmp_path: Path) -> None:
    backend = FakeSandboxes()

    def interrupt_guest(
        args: tuple[str, ...], *, timeout: float, limit: int, input_bytes: bytes
    ) -> ProcessCapture:
        if args[:1] == ("exec",):
            raise KeyboardInterrupt
        return backend.run(args, timeout=timeout, limit=limit, input_bytes=input_bytes)

    runtime = HostRuntime(tmp_path, interrupt_guest)
    runtime.execute(CREATE)
    with pytest.raises(KeyboardInterrupt):
        runtime.execute(("exec", NAME, "sleep", "300"))
    assert backend.calls[-1] == ("stop", NAME)
