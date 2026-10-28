"""One synchronous attempt: explicit canonical flow and terminal PACKAGE."""

import math
from pathlib import Path
from uuid import UUID

from shipyard.agents.base import AgentExecutionError, AgentTimeoutError, NativeAgent
from shipyard.application.budget import BudgetClock, BudgetExceeded, Timing
from shipyard.application.stages import StageExecution, execute_stage
from shipyard.application.verification import TestExecution, execute_test
from shipyard.domain import FailureReason, RunOutcome
from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.playbook_execution import (
    PlaybookExecution,
    StageReceipt,
    StepOutcome,
)
from shipyard.domain.stage_result import AgentStage, InvalidStageOutput, StageStatus
from shipyard.evidence.package import RunEvidence, package_run
from shipyard.git import GitRepository
from shipyard.git.repository import GitReadError, GitWorkspaceError
from shipyard.paths import run_workspace
from shipyard.persistence import FileRunStore
from shipyard.skills import compile_methodology


def execute_run(
    *,
    store: FileRunStore,
    run_id: UUID,
    repository: GitRepository,
    workspace: Path | None = None,
    agent: NativeAgent,
    clock: BudgetClock | None = None,
) -> RunEvidence:
    """Execute once, preserving partial work and terminal evidence.

    Retry/recovery and concurrent local writers are unsupported. PACKAGE failures
    propagate to the caller after terminal state has been persisted.
    """
    contract = store.load(run_id)
    if clock is not None and clock.budget != contract.execution.budget:
        raise ValueError("Clock must use the frozen execution budget")
    if workspace is None:
        workspace = run_workspace(run_id)
    workspace = repository.preflight_workspace(
        base_sha=contract.base_sha, path=workspace
    )
    try:
        workspace.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise GitWorkspaceError(
            f"Cannot prepare workspace {workspace} parent {workspace.parent}: {error}; "
            "check directory access or supply --workspace with a fresh external path"
        ) from error
    run = store.begin(run_id)
    clock = clock or BudgetClock(contract.execution.budget)
    directory = store.directory(run_id)
    attempt = Attempt.create(run_id, contract.base_sha)
    stages: list[StageExecution] = []
    timings: list[Timing] = []
    candidate: Candidate | None = None
    test: TestExecution | None = None
    error_text: str | None = None
    upstream: dict[str, Path] = {}
    try:
        with (directory / "attempt.json").open("x", encoding="utf-8") as output:
            output.write(attempt.model_dump_json())
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
        isolated = repository.create_workspace(attempt=attempt, path=workspace)
        for stage in (
            AgentStage.DESIGN,
            AgentStage.PLAN,
            AgentStage.BUILD,
            AgentStage.REVIEW,
        ):
            mark = clock.mark()
            artifact_stage = ArtifactStage(stage.value)
            try:
                allowance = math.floor(clock.allowance(artifact_stage))
                context = (
                    upstream
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
                # A late response cannot consume another stage's allowance.
                clock.allowance(artifact_stage, admission=False)
                if execution.review_decision is not None:
                    routing = routing.accept(execution.review_decision.receipt)
                    run = run.complete(
                        execution.review_decision.outcome,
                        verification=execution.review_decision.verification,
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
                    candidate = isolated.publish_candidate()
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
            finally:
                timings.append(clock.timing(artifact_stage, mark))
            if stage == AgentStage.BUILD:
                assert candidate is not None
                mark = clock.mark()
                try:
                    allowance = clock.allowance(ArtifactStage.TEST)
                    test = execute_test(
                        contract=contract,
                        attempt=attempt,
                        candidate=candidate,
                        workspace=isolated.path,
                        output_dir=directory / "test",
                        check_timeout_seconds=allowance,
                        total_timeout_seconds=allowance,
                        cleanup_workspace=isolated.clean_ignored_files,
                    )
                    clock.allowance(ArtifactStage.TEST, admission=False)
                    routing = routing.accept(test.receipt)
                    if test.receipt.outcome == StepOutcome.TEST_FAILED:
                        run = run.complete(RunOutcome.TEST_FAILED)
                        break
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
    timing = clock.timing(None)
    store.finish(run)
    with (directory / "timing.json").open("x", encoding="utf-8") as output:
        output.write(timing.model_dump_json())
    with (directory / "stage-timings.json").open("x", encoding="utf-8") as output:
        output.write("[" + ",".join(item.model_dump_json() for item in timings) + "]")
    return package_run(
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
    )
