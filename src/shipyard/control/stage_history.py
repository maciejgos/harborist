"""Read-only timeline recovery from attributed harness records, never prose."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from shipyard.application.review import validate_test_context
from shipyard.application.stages import StageExecution
from shipyard.application.verification import TestExecution
from shipyard.control.queue import Progress
from shipyard.domain import Run, RunContract, RunLifecycle, RunOutcome
from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.stage_result import AgentStage, ReviewStageResult, StageStatus
from shipyard.evidence.package import RunEvidence

ORDER = ("design", "plan", "build", "test", "review")


class StageHistory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stages: dict[str, Progress] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)


def read_stage_history(
    *, directory: Path, contract: RunContract, run: Run, attempt: Attempt
) -> StageHistory:
    stages: dict[str, Progress] = {}
    errors: dict[str, str] = {}
    captures: dict[AgentStage, StageExecution] = {}
    test: TestExecution | None = None
    stopped: str | None = None

    for stage in AgentStage:
        path = directory / stage.value / "manifest.json"
        if not path.exists():
            continue
        try:
            capture = StageExecution.model_validate_json(path.read_bytes())
            if (
                capture.run_id != run.run_id
                or capture.attempt_id != attempt.attempt_id
                or capture.stage != stage
                or capture.output.result.stage != stage
            ):
                raise ValueError(
                    "Stage manifest does not match this Run, Attempt and stage"
                )
            if (
                capture.candidate is not None
                and capture.candidate.attempt_id != attempt.attempt_id
            ):
                raise ValueError("Stage candidate belongs to a different Attempt")
            if stage == AgentStage.REVIEW:
                if (
                    capture.review_decision is None
                    or not isinstance(capture.output.result, ReviewStageResult)
                    or capture.output.result.candidate != capture.candidate
                ):
                    raise ValueError("REVIEW lacks an attributed harness decision")
                if (
                    run.verification is not None
                    and capture.review_decision.verification != run.verification
                ):
                    raise ValueError("REVIEW verification differs from terminal Run")
                state = (
                    "failed"
                    if capture.review_decision.outcome == RunOutcome.CHANGES_REQUIRED
                    else "completed"
                )
                reason = capture.review_decision.outcome.value
            else:
                status = capture.output.result.status
                state = "completed" if status == StageStatus.READY else status.value
                reason = None if status == StageStatus.READY else status.value.upper()
                if status != StageStatus.READY:
                    stopped = stage.value
            captures[stage] = capture
            stages[stage.value] = Progress(
                stage=stage.value, state=state, reason=reason
            )
        except (OSError, ValueError) as error:
            errors[stage.value] = str(error)[:1024]

    path = directory / "test" / "manifest.json"
    if path.exists():
        try:
            test = TestExecution.model_validate_json(path.read_bytes())
            candidate = test.receipt.candidate
            if candidate is None:
                raise ValueError("TEST capture has no candidate")
            if run.verification is not None and candidate != run.verification.candidate:
                raise ValueError(
                    "TEST candidate differs from terminal verified candidate"
                )
            passed = validate_test_context(
                contract=contract, attempt=attempt, candidate=candidate, test=test
            )
            review = captures.get(AgentStage.REVIEW)
            if review is not None and (not passed or review.candidate != candidate):
                stages.pop("review", None)
                errors["review"] = (
                    "REVIEW does not match successful TEST for this candidate"
                )
            stages["test"] = Progress(
                stage="test",
                state="completed" if passed else "failed",
                reason=None if passed else "TEST_FAILED",
            )
            if not passed:
                stopped = "test"
        except (OSError, ValueError) as error:
            test = None
            errors["test"] = str(error)[:1024]

    path = directory / "evidence.json"
    if path.exists():
        try:
            evidence = RunEvidence.model_validate_json(path.read_bytes())
            if (
                evidence.version != 1
                or evidence.run != run
                or evidence.contract != contract
                or evidence.attempt != attempt
                or evidence.package_timing.stage != ArtifactStage.PACKAGE
            ):
                raise ValueError("PACKAGE evidence differs from the frozen Run/Attempt")
            if (
                evidence.candidate is not None
                and evidence.candidate.attempt_id != attempt.attempt_id
            ):
                raise ValueError("PACKAGE candidate belongs to another Attempt")
            if (
                run.verification is not None
                and evidence.candidate != run.verification.candidate
            ):
                raise ValueError(
                    "PACKAGE candidate differs from the verified candidate"
                )
            if test is not None and evidence.candidate != test.receipt.candidate:
                raise ValueError("PACKAGE candidate differs from trusted TEST")
            for capture in evidence.stages:
                if (
                    capture.run_id != run.run_id
                    or capture.attempt_id != attempt.attempt_id
                ):
                    raise ValueError("PACKAGE contains a foreign stage capture")
                if capture.stage in captures and captures[capture.stage] != capture:
                    raise ValueError("PACKAGE disagrees with the saved stage manifest")
            if test is not None and evidence.test != test:
                raise ValueError("PACKAGE disagrees with saved TEST evidence")
            stages["package"] = Progress(stage="package", state="completed")
            if (
                run.lifecycle in (RunLifecycle.FAILED, RunLifecycle.CANCELLED)
                and evidence.stage_timings
            ):
                last = evidence.stage_timings[-1].stage
                if last is not None and last.value in ORDER:
                    stopped = last.value
                    stages[stopped] = Progress(
                        stage=stopped,
                        state="cancelled"
                        if run.lifecycle == RunLifecycle.CANCELLED
                        else "failed",
                        reason=run.failure_reason.value
                        if run.failure_reason
                        else "CANCELLED",
                    )
        except (OSError, ValueError) as error:
            errors["package"] = str(error)[:1024]

    if stopped is not None and run.lifecycle in (
        RunLifecycle.COMPLETED,
        RunLifecycle.FAILED,
        RunLifecycle.CANCELLED,
    ):
        for name in ORDER[ORDER.index(stopped) + 1 :]:
            if name not in stages and name not in errors:
                stages[name] = Progress(
                    stage=name,
                    state="skipped",
                    reason=f"Execution stopped at {stopped.upper()}",
                )
    return StageHistory(stages=stages, errors=errors)
