"""Controlled monotonic deadlines and plain streaming presentation."""

import io

from shipyard.application.progress import ProgressUpdate
from shipyard.domain.artifact import ArtifactStage


def test_reporter_deadlines_and_terminal_output() -> None:
    from shipyard.cli.progress import ProgressReporter

    ticks = [0.0]
    output = io.StringIO()
    reporter = ProgressReporter(stream=output, monotonic=lambda: ticks[0])
    reporter.update(ProgressUpdate(ArtifactStage.BUILD, "started"))
    ticks[0] = 14.99
    reporter.heartbeat()
    assert "running" not in output.getvalue()
    ticks[0] = 15
    reporter.heartbeat()
    reporter.heartbeat()
    assert output.getvalue().count("running") == 1
    assert "15s elapsed; awaiting completion" in output.getvalue()
    ticks[0] = 40
    reporter.heartbeat()
    assert output.getvalue().count("running") == 2
    reporter.update(ProgressUpdate(ArtifactStage.BUILD, "completed"))
    ticks[0] = 100
    reporter.heartbeat()
    assert output.getvalue().endswith("BUILD completed — 40s\n")
    assert "\r" not in output.getvalue() and "\x1b" not in output.getvalue()


def test_reporting_thread_wakes_and_joins_on_exception() -> None:
    import threading

    import pytest

    from shipyard.cli.progress import ProgressReporter

    emitted = threading.Event()

    class Output(io.StringIO):
        def flush(self) -> None:
            if "running" in self.getvalue():
                emitted.set()

    ticks = [0.0]
    output = Output()
    reporter = ProgressReporter(stream=output, monotonic=lambda: ticks[0])
    with pytest.raises(RuntimeError), reporter:
        reporter.update(ProgressUpdate(ArtifactStage.TEST, "started"))
        with reporter.condition:
            ticks[0] = 15
            reporter.condition.notify_all()
        assert emitted.wait(2)
        raise RuntimeError("failure")
    assert reporter.thread is not None and not reporter.thread.is_alive()
    before = output.getvalue()
    ticks[0] = 100
    reporter.heartbeat()
    assert output.getvalue() == before


def test_broken_stderr_is_presentation_only() -> None:
    from shipyard.cli.progress import ProgressReporter

    class Broken(io.StringIO):
        def write(self, text: str) -> int:
            raise OSError("private payload")

    with ProgressReporter(stream=Broken()) as reporter:
        reporter.update(ProgressUpdate(ArtifactStage.DESIGN, "started"))
        reporter.update(ProgressUpdate(ArtifactStage.DESIGN, "completed"))
    assert reporter.disabled
