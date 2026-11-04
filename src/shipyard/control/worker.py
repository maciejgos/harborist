"""Serial queue consumer delegating all workflow rules to execute_run."""

from shipyard.agents.base import NativeAgent
from shipyard.application.execution import execute_run
from shipyard.application.progress import ProgressUpdate
from shipyard.control.queue import Progress, QueueRecord, QueueStore
from shipyard.git import GitRepository
from shipyard.persistence import FileRunStore
from shipyard.persistence.continuation import prepare_continuation


class Worker:
    def __init__(self, queue: QueueStore, *, agent: NativeAgent) -> None:
        self.queue = queue
        self.agent = agent

    def execute_next(self) -> bool:
        record = self.queue.claim()
        if record is None:
            return False
        self.execute(record)
        return True

    def execute(self, record: QueueRecord) -> None:
        submission = record.submission

        def progress(update: ProgressUpdate) -> None:
            self.queue.update_progress(
                submission.run_id,
                Progress(
                    stage=update.stage.value, state=update.state, reason=update.reason
                ),
            )

        try:
            store = FileRunStore(root=submission.runs_root)
            if submission.continuation is not None:
                store, _ = prepare_continuation(
                    store=store,
                    run_id=submission.run_id,
                    request=submission.continuation,
                )
            execute_run(
                store=store,
                run_id=submission.run_id,
                repository=GitRepository(path=submission.repository),
                workspace=submission.workspace,
                agent=self.agent,
                progress=progress,
            )
        except Exception as error:  # noqa: BLE001 - delivery failure, never workflow inference
            self.queue.finish(
                submission.run_id, error=f"{type(error).__name__}: {error}"
            )
        else:
            self.queue.finish(submission.run_id)
