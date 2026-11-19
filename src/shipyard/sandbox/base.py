"""Small execution ports consumed by the synchronous Run orchestrator."""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from shipyard.agents.base import NativeAgent
from shipyard.domain.sandbox import SandboxPolicy
from shipyard.execution.process import ProcessCapture


class SandboxWorkspace(Protocol):
    def capture(
        self, command: list[str], *, cwd: Path, timeout: float, limit: int
    ) -> ProcessCapture: ...

    def require_unchanged(self) -> None: ...


class SandboxRuntime(Protocol):
    def agent(self, *, policy: SandboxPolicy, receipts: Path) -> NativeAgent: ...

    def workspace(
        self,
        *,
        policy: SandboxPolicy,
        workspace: Path,
        seconds: float,
        label: str,
        receipts: Path,
    ) -> AbstractContextManager[SandboxWorkspace]: ...
