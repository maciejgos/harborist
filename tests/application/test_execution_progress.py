"""Progress describes accepted stage work without changing routing."""

from pathlib import Path

import pytest

from harborist.application.execution import execute_run
from harborist.domain import RunContract
from tests.application.test_run_execution import FakeAgent, capture


@pytest.mark.parametrize(
    "mode,check,reason",
    [
        ("verified", "exit 0", "VERIFIED"),
        ("verified", "exit 1", "TEST_FAILED"),
        ("cancel", "exit 0", "CANCELLED"),
        ("clarify", "exit 0", "NEEDS_CLARIFICATION"),
    ],
)
def test_progress_lifecycle(
    tmp_path: Path, frozen_contract: RunContract, mode: str, check: str, reason: str
) -> None:
    from harborist.application.progress import ProgressUpdate

    updates: list[ProgressUpdate] = []
    store, repo, contract = capture(tmp_path, frozen_contract, check)
    execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent(mode),
        progress=updates.append,
    )
    assert all(update.stage.value != "intake" for update in updates)
    assert [(u.stage.value, u.state) for u in updates[-2:]] == [
        ("package", "started"),
        ("package", "completed"),
    ]
    for stage in ("design", "plan", "build", "test", "review"):
        events = [u for u in updates if u.stage.value == stage]
        assert [u.state for u in events] in (
            ["started", "completed"],
            ["started", "failed"],
            ["started", "cancelled"],
            ["skipped"],
        )
    if reason == "TEST_FAILED":
        assert any(
            u.stage.value == "test" and u.state == "failed" and u.reason == reason
            for u in updates
        )
        assert any(u.stage.value == "review" and u.state == "skipped" for u in updates)
    if reason == "NEEDS_CLARIFICATION":
        assert updates[1].reason == reason


@pytest.mark.parametrize("boundary", ["design", "test", "package"])
def test_progress_streams_while_synchronous_work_is_blocked(
    tmp_path: Path,
    frozen_contract: RunContract,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    import io
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from harborist.application import execution
    from harborist.cli.progress import ProgressReporter

    entered = threading.Event()
    release = threading.Event()
    emitted = threading.Event()
    ticks = [0.0]

    class Output(io.StringIO):
        def flush(self) -> None:
            if f"{boundary.upper()} running" in self.getvalue():
                emitted.set()

    name = {
        "design": "execute_stage",
        "test": "execute_test",
        "package": "package_run",
    }[boundary]
    original = getattr(execution, name)

    from harborist.domain.stage_result import AgentStage

    def blocking(**kwargs: object) -> object:
        if boundary != "design" or kwargs["stage"] == AgentStage.DESIGN:
            entered.set()
            assert release.wait(5)
        return original(**kwargs)

    monkeypatch.setattr(execution, name, blocking)
    store, repo, contract = capture(tmp_path, frozen_contract)
    output = Output()
    with (
        ProgressReporter(stream=output, monotonic=lambda: ticks[0]) as reporter,
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(
            execute_run,
            store=store,
            run_id=contract.run_id,
            repository=repo,
            workspace=tmp_path / "work",
            agent=FakeAgent(),
            progress=reporter.update,
        )
        try:
            assert entered.wait(3)
            with reporter.condition:
                ticks[0] = 15
                reporter.condition.notify_all()
            assert emitted.wait(2)
            assert not future.done()
        finally:
            release.set()
        assert future.result(timeout=5).run.outcome is not None
    assert reporter.thread is not None and not reporter.thread.is_alive()


@pytest.mark.parametrize("mode", ["failure", "invalid", "rescope", "changes"])
def test_progress_failure_and_early_outcome_reasons(
    tmp_path: Path, frozen_contract: RunContract, mode: str
) -> None:
    from harborist.application.progress import ProgressUpdate

    updates: list[ProgressUpdate] = []
    store, repo, contract = capture(tmp_path, frozen_contract)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent(mode),
        progress=updates.append,
    )
    reason = str(result.run.failure_reason or result.run.outcome)
    assert any(u.reason == reason for u in updates)
    assert not any(u.state == "started" and u.stage.value == "intake" for u in updates)


def test_candidate_publication_failure_does_not_complete_build(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harborist.application.progress import ProgressUpdate
    from harborist.git.repository import GitWorkspace, GitWorkspaceError

    def broken(self: GitWorkspace, *, message: str) -> None:
        raise GitWorkspaceError("sensitive task content")

    monkeypatch.setattr(GitWorkspace, "publish_candidate", broken)
    updates: list[ProgressUpdate] = []
    store, repo, contract = capture(tmp_path, frozen_contract)
    execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent(),
        progress=updates.append,
    )
    assert [u.state for u in updates if u.stage.value == "build"] == [
        "started",
        "failed",
    ]
    assert [u.state for u in updates if u.stage.value == "test"] == ["skipped"]
    assert "sensitive task content" not in str(updates)
