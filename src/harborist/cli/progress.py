"""Plain stderr progress with a transient presentation-only timer."""

import sys
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Self, TextIO

from harborist.application.progress import ProgressUpdate


def duration(seconds: float) -> str:
    elapsed = max(0, int(seconds))
    minutes, seconds = divmod(elapsed, 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"


class ProgressReporter:
    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.stream = stream if stream is not None else sys.stderr
        self.monotonic = monotonic
        self.condition = threading.Condition()
        self.active: str | None = None
        self.started = 0.0
        self.deadline = 0.0
        self.stopped = False
        self.disabled = False
        self.thread: threading.Thread | None = None
        self.last: ProgressUpdate | None = None

    def _write(self, text: str) -> None:
        if not self.disabled:
            try:
                self.stream.write(text + "\n")
                self.stream.flush()
            except Exception:  # noqa: BLE001 - presentation must not change Run results
                self.disabled = True

    def line(self, text: str) -> None:
        with self.condition:
            self._write(text)

    def update(self, update: ProgressUpdate) -> None:
        with self.condition:
            if self.stopped:
                return
            self.last = update
            now = self.monotonic()
            stage = update.stage.value.upper()
            suffix = ""
            if update.state == "started":
                self.active = stage
                self.started = now
                self.deadline = now + 15
            elif self.active == stage:
                suffix = f" — {duration(now - self.started)}"
                self.active = None
            reason = f" ({update.reason})" if update.reason else ""
            self._write(f"{stage} {update.state}{suffix}{reason}")
            self.condition.notify_all()

    def heartbeat(self) -> None:
        with self.condition:
            now = self.monotonic()
            if not self.stopped and self.active is not None and now >= self.deadline:
                self._write(
                    f"{self.active} running — {duration(now - self.started)} elapsed; awaiting completion"
                )
                self.deadline = now + 15

    def _run(self) -> None:
        with self.condition:
            while not self.stopped:
                self.heartbeat()
                timeout = (
                    max(0, self.deadline - self.monotonic()) if self.active else None
                )
                self.condition.wait(timeout)

    def __enter__(self) -> Self:
        self.thread = threading.Thread(
            target=self._run, name="harborist-progress", daemon=True
        )
        self.thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        with self.condition:
            self.stopped = True
            self.active = None
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join()
