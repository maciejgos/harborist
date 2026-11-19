"""One synchronous attempt: explicit canonical flow and terminal PACKAGE."""

import hashlib
import json
import math
from contextlib import nullcontext
from pathlib import Path
from uuid import UUID

from shipyard.agents.base import AgentExecutionError, AgentTimeoutError, NativeAgent
from shipyard.application.budget import BudgetClock, BudgetExceeded, Timing
from shipyard.application.candidate_message import candidate_message
from shipyard.application.progress import ExecutionProgress, ProgressCallback
from shipyard.application.stages import StageExecution, execute_stage
from shipyard.application.verification import TestExecution, execute_test
from shipyard.application.workspace import validate_workspace_placement
from shipyard.domain import FailureReason, RunOutcome
from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.playbook_execution import (
    PlaybookExecution,
    StageReceipt,
    StepOutcome,
)
from shipyard.domain.sandbox import SandboxPolicy
from shipyard.domain.stage_result import AgentStage, InvalidStageOutput, StageStatus
from shipyard.evidence.package import RunEvidence, package_run
from shipyard.execution.cancellation import check_cancellation
from shipyard.execution.process import capture_process
from shipyard.git import GitRepository
from shipyard.git.command import run_git
from shipyard.git.repository import GitReadError, GitWorkspaceError
from shipyard.paths import legacy_run_workspace
from shipyard.persistence import FileRunStore
from shipyard.persistence.continuation import execution_lock, load_continuation
from shipyard.persistence.retirement import require_live_run
from shipyard.persistence.workspace import (
    WorkspaceSelection,
    load_layout,
    load_selection,
)
from shipyard.sandbox.base import SandboxRuntime
from shipyard.skills import compile_methodology


def execute_run(
    *,
    store: FileRunStore,
    run_id: UUID,
    repository: GitRepository,
    workspace: Path | None = None,
    agent: NativeAgent,
    clock: BudgetClock | None = None,
    progress: ProgressCallback | None = None,
    runtime: SandboxRuntime | None = None,
) -> RunEvidence:
    """Execute one fresh Attempt under the local Run execution lock."""
    with execution_lock(store, run_id):
        require_live_run(store.original_directory(run_id).parent, run_id)
        return _execute_run(
            store=store.pinned(run_id),
            run_id=run_id,
            repository=repository,
            workspace=workspace,
            agent=agent,
            clock=clock,
            progress=progress,
            runtime=runtime,
        )


def _execute_run(
    *,
    store: FileRunStore,
    run_id: UUID,
    repository: GitRepository,
    workspace: Path | None,
    agent: NativeAgent,
    clock: BudgetClock | None,
    progress: ProgressCallback | None,
    runtime: SandboxRuntime | None,
) -> RunEvidence:
    """Execute once, preserving partial work and terminal evidence.

    Continuations use an explicit durable admission and fresh upstream inputs.
    PACKAGE failures propagate after terminal state has been persisted.
    """
    updates = ExecutionProgress(progress)
    contract = store.load(run_id)
    if clock is not None and clock.budget != contract.execution.budget:
        raise ValueError("Clock must use the frozen execution budget")
    directory = store.directory(run_id)
    continuation = (
        load_continuation(store, run_id) if store.selected_number(run_id) else None
    )
    if clock is not None and (
        clock.spent_seconds != (continuation.spent_seconds if continuation else 0)
        or clock.granted_seconds
        != (continuation.granted_seconds if continuation else 0)
    ):
        raise ValueError("Clock must use the recorded spending and grants")
    selection = load_selection(directory, run_id)
    if workspace is None:
        if continuation is not None:
            workspace = (
                store.original_directory(run_id).parent.parent
                / "workspaces"
                / str(run_id)
                / str(continuation.attempt.attempt_id)
            )
        elif selection is not None:
            workspace = selection.path
        elif load_layout(directory, run_id) is not None:
            workspace = directory / "workspace"
        else:
            workspace = legacy_run_workspace(run_id)
    validate_workspace_placement(path=workspace, run_directory=directory)
    workspace = repository.preflight_workspace(
        base_sha=continuation.attempt.start_sha if continuation else contract.base_sha,
        path=workspace,
    )
    try:
        workspace.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise GitWorkspaceError(
            f"Cannot prepare workspace {workspace} parent {workspace.parent}: {error}; "
            "check directory access or supply --workspace with a fresh external path"
        ) from error
    admitted_path = directory / "execution-workspace.json"
    if admitted_path.exists() or admitted_path.is_symlink():
        raise GitWorkspaceError(
            f"Invalid workspace {workspace}: retained execution association {admitted_path}; "
            "inspect retained data; use a separate intake for a new Run, not --workspace to retry"
        )
    run = store.begin(run_id)
    clock = clock or BudgetClock(
        contract.execution.budget,
        spent_seconds=continuation.spent_seconds if continuation else 0,
        granted_seconds=continuation.granted_seconds if continuation else 0,
    )
    directory = store.directory(run_id)
    attempt = (
        continuation.attempt
        if continuation
        else Attempt.create(run_id, contract.base_sha)
    )
    stages: list[StageExecution] = []
    timings: list[Timing] = []
    candidate: Candidate | None = None
    test: TestExecution | None = None
    error_text: str | None = None
    upstream: dict[str, Path] = {}
    if continuation is not None and continuation.spec_digest is not None:
        upstream["spec.md"] = directory / "frozen-spec.md"
    try:
        with (directory / "attempt.json").open("x", encoding="utf-8") as output:
            output.write(attempt.model_dump_json())
        with admitted_path.open("x", encoding="utf-8") as output:
            output.write(
                WorkspaceSelection(
                    run_id=run_id, attempt_id=attempt.attempt_id, path=workspace
                ).model_dump_json()
            )
        check_cancellation()
        try:
            methodology = compile_methodology(contract.execution)
        except ValueError:
            run = run.fail(FailureReason.CONFIGURATION_ERROR)
            raise
        routing = PlaybookExecution(
            playbook=methodology.playbook.definition, attempt=attempt
        )
        routing = routing.accept(
            StageReceipt(stage=ArtifactStage.INTAKE, outcome=StepOutcome.SUCCEEDED)
        )
        validate_workspace_placement(path=workspace, run_directory=directory)
        if "spec.md" in upstream:
            routing = routing.accept(
                StageReceipt(stage=ArtifactStage.DESIGN, outcome=StepOutcome.SUCCEEDED)
            )
        isolated = repository.create_workspace(attempt=attempt, path=workspace)
        policy = contract.execution.sandbox_policy
        if isinstance(policy, SandboxPolicy):
            if runtime is None:
                raise AgentExecutionError(
                    "The selected sandbox runtime is not configured; host execution is disabled"
                )
            agent = runtime.agent(policy=policy, receipts=directory / "sandbox")
        for stage in (
            AgentStage.DESIGN,
            AgentStage.PLAN,
            AgentStage.BUILD,
            AgentStage.REVIEW,
        ):
            check_cancellation()
            if stage == AgentStage.DESIGN and "spec.md" in upstream:
                updates.emit(ArtifactStage.DESIGN, "skipped", "FROZEN_SPEC_REUSED")
                continue
            mark = clock.mark()
            artifact_stage = ArtifactStage(stage.value)
            try:
                allowance = math.floor(clock.allowance(artifact_stage))
                context = (
                    dict(upstream)
                    if stage != AgentStage.REVIEW
                    else {
                        "spec.md": upstream["spec.md"],
                        "test-evidence.json": directory / "test" / "manifest.json",
                        **(
                            {"build-process.json": upstream["build-process.json"]}
                            if "build-process.json" in upstream
                            else {}
                        ),
                    }
                )
                if stage == AgentStage.PLAN and continuation is not None:
                    context["continuation-context.json"] = (
                        directory / "continuation-context.json"
                    )
                updates.emit(artifact_stage, "started")
                execution = execute_stage(
                    contract=contract,
                    attempt=attempt,
                    stage=stage,
                    workspace=isolated.path,
                    upstream=context,
                    output_dir=directory / stage.value,
                    agent=agent,
                    remaining_seconds=allowance,
                    candidate=candidate if stage == AgentStage.REVIEW else None,
                    test_receipt=test.receipt
                    if stage == AgentStage.REVIEW and test
                    else None,
                )
                stages.append(execution)
                check_cancellation()
                # A late response cannot consume another stage's allowance.
                clock.allowance(artifact_stage, admission=False)
                if execution.review_decision is not None:
                    routing = routing.accept(execution.review_decision.receipt)
                    run = run.complete(
                        execution.review_decision.outcome,
                        verification=execution.review_decision.verification,
                    )
                    updates.emit(
                        artifact_stage,
                        "completed",
                        execution.review_decision.outcome.value,
                    )
                    break
                status = execution.output.result.status
                if status != StageStatus.READY:
                    outcome = RunOutcome(status.value.upper())
                    routing = routing.accept(
                        StageReceipt(
                            stage=artifact_stage, outcome=StepOutcome(status.value)
                        )
                    )
                    run = run.complete(outcome)
                    updates.emit(artifact_stage, "completed", outcome.value)
                    break
                if stage == AgentStage.DESIGN:
                    upstream["spec.md"] = directory / "design" / "spec.md"
                elif stage == AgentStage.PLAN:
                    upstream["plan.md"] = directory / "plan" / "plan.md"
                elif stage == AgentStage.BUILD:
                    if execution.output.process_report is not None:
                        upstream["build-process.json"] = (
                            directory / "build" / "build-process.json"
                        )
                    candidate = isolated.publish_candidate(
                        message=candidate_message(
                            intent=contract.intent, attempt=attempt
                        ),
                        attempt_scoped=continuation is not None,
                    )
                    if isinstance(policy, SandboxPolicy):
                        bundle = directory / "sandbox" / "candidate.bundle"
                        run_git(isolated.path, "bundle", "create", str(bundle), "HEAD")
                        (bundle.parent / "candidate.json").write_text(
                            json.dumps(
                                {
                                    "candidate": candidate.model_dump(mode="json"),
                                    "start_sha": attempt.start_sha,
                                    "sha256": hashlib.sha256(
                                        bundle.read_bytes()
                                    ).hexdigest(),
                                    "size_bytes": bundle.stat().st_size,
                                }
                            )
                        )
                    clock.allowance(artifact_stage, admission=False)
                    if execution.output.plan_update is not None:
                        upstream["plan.md"] = directory / "build" / "plan.md"
                routing = routing.accept(
                    StageReceipt(
                        stage=artifact_stage,
                        outcome=StepOutcome.SUCCEEDED,
                        candidate=candidate if stage == AgentStage.BUILD else None,
                    )
                )
                updates.emit(artifact_stage, "completed")
            finally:
                timings.append(clock.timing(artifact_stage, mark))
            if stage == AgentStage.BUILD:
                assert candidate is not None
                mark = clock.mark()
                try:
                    allowance = clock.allowance(ArtifactStage.TEST)
                    updates.emit(ArtifactStage.TEST, "started")
                    with (
                        runtime.workspace(
                            policy=policy,
                            workspace=isolated.path,
                            seconds=allowance,
                            label="test",
                            receipts=directory / "sandbox",
                        )
                        if isinstance(policy, SandboxPolicy) and runtime is not None
                        else nullcontext()
                    ) as guest:
                        test = execute_test(
                            contract=contract,
                            attempt=attempt,
                            candidate=candidate,
                            workspace=isolated.path,
                            output_dir=directory / "test",
                            check_timeout_seconds=allowance,
                            total_timeout_seconds=allowance,
                            cleanup_workspace=guest.require_unchanged
                            if guest
                            else isolated.clean_ignored_files,
                            executor=guest.capture if guest else capture_process,
                        )
                    check_cancellation()
                    clock.allowance(ArtifactStage.TEST, admission=False)
                    routing = routing.accept(test.receipt)
                    if test.receipt.outcome == StepOutcome.TEST_FAILED:
                        run = run.complete(RunOutcome.TEST_FAILED)
                        updates.emit(ArtifactStage.TEST, "failed", "TEST_FAILED")
                        break
                    updates.emit(ArtifactStage.TEST, "completed")
                finally:
                    timings.append(clock.timing(ArtifactStage.TEST, mark))
    except KeyboardInterrupt:
        run = run.cancel()
        error_text = "Execution cancelled by operator"
    except (BudgetExceeded, AgentTimeoutError) as error:
        run = run.fail(FailureReason.TIME_BUDGET_EXCEEDED)
        error_text = str(error)[:4096]
    except InvalidStageOutput as error:
        run = run.fail(FailureReason.INVALID_STAGE_OUTPUT)
        error_text = str(error)[:4096]
    except (AgentExecutionError, GitReadError, GitWorkspaceError) as error:
        run = run.fail(FailureReason.EXECUTION_FAILED)
        error_text = str(error)[:4096]
    except Exception as error:  # noqa: BLE001 - finalization boundary for unexpected executor failures
        if run.failure_reason is None:
            run = run.fail(FailureReason.INTERNAL_ERROR)
        error_text = f"{type(error).__name__}: {error}"[:4096]
    updates.terminal(
        str(run.failure_reason or run.outcome or run.lifecycle),
        cancelled=run.lifecycle.value == "CANCELLED",
    )
    timing = clock.timing(None)
    try:
        store.finish(run)
        with (directory / "timing.json").open("x", encoding="utf-8") as output:
            output.write(timing.model_dump_json())
        with (directory / "stage-timings.json").open("x", encoding="utf-8") as output:
            output.write(
                "[" + ",".join(item.model_dump_json() for item in timings) + "]"
            )
    except BaseException:
        updates.emit(ArtifactStage.PACKAGE, "skipped", "FINALIZATION_FAILED")
        raise
    updates.emit(ArtifactStage.PACKAGE, "started")
    try:
        evidence = package_run(
            directory=directory,
            contract=contract,
            run=run,
            attempt=attempt,
            candidate=candidate,
            stages=tuple(stages),
            test=test,
            timing=timing,
            stage_timings=tuple(timings),
            error=error_text,
            workspace=workspace,
            reused_specification=upstream.get("spec.md")
            if continuation and continuation.spec_digest
            else None,
        )
    except BaseException as error:
        updates.emit(
            ArtifactStage.PACKAGE,
            "cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
            "PACKAGE_FAILED",
        )
        raise
    updates.emit(ArtifactStage.PACKAGE, "completed")
    return evidence
