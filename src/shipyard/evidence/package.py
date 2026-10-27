"""Create-only PACKAGE output; no executor or budget admission is required."""

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from shipyard.application.budget import Timing
from shipyard.application.review import evaluate_review, validate_test_context
from shipyard.application.stages import StageExecution
from shipyard.application.verification import TestExecution
from shipyard.domain import Run, RunContract, RunLifecycle, RunOutcome
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.stage_result import ReviewStageResult


class EvidenceFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str


class RunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int = 1
    run: Run
    contract: RunContract
    attempt: Attempt | None
    candidate: Candidate | None
    timing: Timing
    stage_timings: tuple[Timing, ...]
    stages: tuple[StageExecution, ...]
    test: TestExecution | None
    files: tuple[EvidenceFile, ...]
    unverified: tuple[str, ...]
    error: str | None


def _files(directory: Path) -> tuple[EvidenceFile, ...]:
    files: list[EvidenceFile] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Evidence may not contain symlinks")
        if path.is_file():
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as stream:
                while chunk := stream.read(65536):
                    size += len(chunk)
                    digest.update(chunk)
            files.append(
                EvidenceFile(
                    path=path.relative_to(directory).as_posix(),
                    size_bytes=size,
                    sha256=digest.hexdigest(),
                )
            )
    return tuple(files)


def package_run(
    *,
    directory: Path,
    contract: RunContract,
    run: Run,
    timing: Timing,
    attempt: Attempt | None = None,
    candidate: Candidate | None = None,
    stages: tuple[StageExecution, ...] = (),
    test: TestExecution | None = None,
    stage_timings: tuple[Timing, ...] = (),
    error: str | None = None,
) -> RunEvidence:
    """Publish report first and evidence index last; preserve partial failures.

    The private directory reservation rejects retries, including partial PACKAGE.
    Filesystem failure cannot guarantee a report; callers must surface that error.
    Terminal immutability is enforced by the synchronous executor's exclusive
    reservation, not by OS permissions against other local processes.
    """
    run = Run.model_validate_json(run.model_dump_json())
    contract = RunContract.model_validate_json(contract.model_dump_json())
    if run.lifecycle not in (
        RunLifecycle.COMPLETED,
        RunLifecycle.FAILED,
        RunLifecycle.CANCELLED,
    ):
        raise ValueError("PACKAGE requires a terminal Run")
    if run.run_id != contract.run_id or (
        attempt is not None and attempt.run_id != run.run_id
    ):
        raise ValueError("PACKAGE identities must belong to the frozen Run")
    if candidate is not None and (
        attempt is None or candidate.attempt_id != attempt.attempt_id
    ):
        raise ValueError("Candidate must belong to the packaged Attempt")
    for stage in stages:
        if (
            attempt is None
            or stage.run_id != run.run_id
            or stage.attempt_id != attempt.attempt_id
            or (stage.candidate is not None and stage.candidate != candidate)
        ):
            raise ValueError("Stage identity must match packaged Run and candidate")
    if test is not None:
        if attempt is None or candidate is None:
            raise ValueError("TEST requires Attempt and candidate")
        validate_test_context(
            contract=contract, attempt=attempt, candidate=candidate, test=test
        )
    if run.outcome == RunOutcome.VERIFIED:
        if attempt is None or candidate is None or test is None:
            raise ValueError("VERIFIED PACKAGE requires complete verification evidence")
        reviews = [s for s in stages if isinstance(s.output.result, ReviewStageResult)]
        designs = [s for s in stages if s.stage.value == "design"]
        if len(reviews) != 1 or len(designs) != 1:
            raise ValueError("VERIFIED PACKAGE requires DESIGN and REVIEW")
        review = reviews[0].output.result
        assert isinstance(review, ReviewStageResult)
        decision = evaluate_review(
            contract=contract,
            attempt=attempt,
            candidate=candidate,
            test=test,
            specification=designs[0].output.artifact or "",
            review=review,
        )
        if decision.verification != run.verification:
            raise ValueError("Packaged verification must match terminal Run")
    missing: list[str] = []
    if candidate is None:
        missing.append("No candidate commit was produced")
    if test is None:
        missing.append("Trusted TEST evidence unavailable")
    if not any(stage.stage.value == "review" for stage in stages):
        missing.append("Independent REVIEW unavailable; acceptance criteria unverified")
    if run.outcome != RunOutcome.VERIFIED:
        missing.append("This Run does not establish a VERIFIED software outcome")
    if any(stage.usage is None for stage in stages) or not stages:
        missing.append(
            "Provider usage unavailable for some or all invocations; cost UNKNOWN"
        )
    # Inspect before creating any outputs and refuse foreign persisted records.
    _files(directory)
    for name, expected in (("run.json", run), ("contract.json", contract)):
        path = directory / name
        if (
            path.exists()
            and type(expected).model_validate_json(path.read_bytes()) != expected
        ):
            raise ValueError(f"Persisted {name} differs from PACKAGE context")
    (directory / ".package").mkdir()
    status = run.outcome or run.failure_reason or run.lifecycle
    lines = [
        "# Shipyard Run report",
        "",
        f"Run: `{run.run_id}`",
        f"Lifecycle: {run.lifecycle}",
        f"Result: {status}",
        f"Base: `{contract.base_sha}`",
        f"Candidate: `{candidate.candidate_sha}`"
        if candidate
        else "Candidate: unavailable",
        "",
        f"Started: {timing.started_at.isoformat()}",
        f"Ended: {timing.ended_at.isoformat()}",
        f"Execution duration: {timing.duration_seconds:.3f}s",
        f"Budget: {timing.original_seconds}s; remaining: {timing.remaining_seconds:.3f}s",
        "PACKAGE is outside the execution budget.",
        "",
        "## Provenance",
        "",
        f"Agent: {contract.execution.agent_profile.name} / {contract.execution.agent_profile.model}",
        f"Playbook: {contract.execution.playbook.name} / {contract.execution.playbook.sha256}",
        f"Verification configuration: {contract.verification.source_sha256}",
    ]
    lines.extend(
        f"Skill: {skill.name} / {skill.sha256}" for skill in contract.execution.skills
    )
    lines.extend(["", "## Checks", ""])
    if test:
        lines.extend(
            f"- {c.id}: {'PASS' if c.passed else 'FAIL'}; exit={c.returncode}; timeout={c.timed_out}; logs truncated={c.stdout_truncated or c.stderr_truncated}"
            for c in test.collection.checks
        )
    else:
        lines.append("Unavailable")
    lines.extend(["", "## Acceptance criteria", ""])
    for stage in stages:
        if isinstance(stage.output.result, ReviewStageResult):
            lines.extend(
                f"- {c.criterion_id}: {c.status.value.upper()}"
                for c in stage.output.result.criteria
            )
    lines.extend(["", "## Time and usage", ""])
    for item in stage_timings:
        lines.append(
            f"- {item.stage}: {item.started_at.isoformat()} → {item.ended_at.isoformat()} ({item.duration_seconds:.3f}s)"
        )
    for stage in stages:
        usage = stage.usage
        lines.append(
            f"- {stage.stage} usage: {usage.model_dump_json() if usage else 'UNKNOWN'}"
        )
        lines.append(
            f"  Actual cost: {str(usage.actual_cost) + ' ' + str(usage.currency) if usage and usage.actual_cost is not None else 'UNKNOWN'}"
        )
    lines.extend(
        [
            "",
            "## Unverified areas and limitations",
            "",
            *[f"- {item}" for item in missing],
        ]
    )
    if error:
        lines.extend(["", "## Execution error", "", error[:4096]])
    with (directory / "report.md").open("x", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")
    evidence = RunEvidence(
        run=run,
        contract=contract,
        attempt=attempt,
        candidate=candidate,
        timing=timing,
        stage_timings=stage_timings,
        stages=stages,
        test=test,
        files=_files(directory),
        unverified=tuple(missing),
        error=error,
    )
    with (directory / "evidence.json").open("x", encoding="utf-8") as output:
        output.write(evidence.model_dump_json(indent=2))
    return evidence
