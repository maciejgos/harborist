"""Optional presentation notifications; never workflow authority."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from harborist.domain.artifact import ArtifactStage

ProgressState = Literal["started", "completed", "failed", "cancelled", "skipped"]


@dataclass(frozen=True)
class ProgressUpdate:
    stage: ArtifactStage
    state: ProgressState
    reason: str | None = None


ProgressCallback = Callable[[ProgressUpdate], None]


class ExecutionProgress:
    """Track active/unreached stages for one synchronous invocation."""

    def __init__(self, callback: ProgressCallback | None) -> None:
        self.callback = callback
        self.started: set[ArtifactStage] = set()
        self.finished: set[ArtifactStage] = set()
        self.active: ArtifactStage | None = None

    def emit(
        self, stage: ArtifactStage, state: ProgressState, reason: str | None = None
    ) -> None:
        if state != "started":
            self.finished.add(stage)
        if state == "started":
            self.started.add(stage)
            self.active = stage
        elif self.active == stage:
            self.active = None
        if self.callback is not None:
            try:
                self.callback(ProgressUpdate(stage, state, reason))
            except Exception:  # noqa: BLE001 - presentation cannot decide execution state
                self.callback = None

    def terminal(self, reason: str, *, cancelled: bool = False) -> None:
        if self.active is not None:
            self.emit(self.active, "cancelled" if cancelled else "failed", reason)
        for stage in ArtifactStage:
            if (
                stage not in (ArtifactStage.INTAKE, ArtifactStage.PACKAGE)
                and stage not in self.started
                and stage not in self.finished
            ):
                self.emit(stage, "skipped", reason)
