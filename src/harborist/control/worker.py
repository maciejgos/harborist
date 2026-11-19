"""Serial queue consumer delegating all workflow rules to execute_run."""

from harborist.agents.base import NativeAgent
from harborist.application.execution import execute_run
from harborist.application.progress import ProgressUpdate
from harborist.control.queue import Progress, QueueRecord, QueueStore
from harborist.execution.cancellation import cancellation_check
from harborist.git import GitRepository
from harborist.persistence import FileRunStore
from harborist.persistence.continuation import prepare_continuation
from harborist.persistence.retirement import load_retirement
from harborist.sandbox.base import SandboxRuntime
from harborist.sandbox.docker import DockerSandboxRuntime


class Worker:
    def __init__(
        self,
        queue: QueueStore,
        *,
        agent: NativeAgent,
        runtime: SandboxRuntime | None = None,
    ) -> None:
        self.queue = queue
        self.agent = agent
        self.runtime = runtime if runtime is not None else DockerSandboxRuntime()

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

        def cancelled() -> bool:
            return load_retirement(submission.runs_root, submission.run_id) is not None

        token = cancellation_check.set(cancelled)
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
                runtime=self.runtime,
            )
        except Exception as error:  # noqa: BLE001 - delivery failure, never workflow inference
            self.queue.finish(
                submission.run_id,
                error=None if cancelled() else f"{type(error).__name__}: {error}",
                cancelled=cancelled(),
            )
        else:
            self.queue.finish(submission.run_id, cancelled=cancelled())
        finally:
            cancellation_check.reset(token)
