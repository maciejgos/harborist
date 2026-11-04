"""Create-only PACKAGE output; no executor or budget admission is required."""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from shipyard.application.budget import Timing
from shipyard.application.review import evaluate_review, validate_test_context
from shipyard.application.stages import StageExecution
from shipyard.application.verification import TestExecution
from shipyard.application.workspace import validate_workspace_placement
from shipyard.domain import Run, RunContract, RunLifecycle, RunOutcome
from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.stage_result import ReviewStageResult
from shipyard.persistence.workspace import load_layout, load_selection


class EvidenceFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str


class RunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int = 1
    reused_spec_sha256: str | None = None
    workspace: Path | None = None
    run: Run
    contract: RunContract
    attempt: Attempt | None
    candidate: Candidate | None
    timing: Timing
    stage_timings: tuple[Timing, ...]
    package_timing: Timing
    stages: tuple[StageExecution, ...]
    test: TestExecution | None
    files: tuple[EvidenceFile, ...]
    unverified: tuple[str, ...]
    error: str | None


def _files(directory: Path, excluded: Path | None = None) -> tuple[EvidenceFile, ...]:
    files: list[EvidenceFile] = []

    def visit(parent: Path) -> None:
        for path in sorted(parent.iterdir()):
            if path == excluded:
                if path.is_symlink():
                    raise ValueError("Workspace root must not be a symlink")
                continue
            if path.is_symlink():
                raise ValueError("Evidence may not contain symlinks")
            if path.is_dir():
                visit(path)
            elif path.is_file():
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

    visit(directory)
    return tuple(sorted(files, key=lambda item: item.path))


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
    workspace: Path | None = None,
    reused_specification: Path | None = None,
) -> RunEvidence:
    """Publish report first and evidence index last; preserve partial failures.

    The private directory reservation rejects retries, including partial PACKAGE.
    Filesystem failure cannot guarantee a report; callers must surface that error.
    Terminal immutability is enforced by the synchronous executor's exclusive
    reservation, not by OS permissions against other local processes.
    """
    package_start = time.monotonic()
    package_started_at = datetime.now(UTC)
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
    reused_spec: str | None = None
    if reused_specification is not None:
        from shipyard.persistence.continuation import ContinuationRecord

        record = ContinuationRecord.model_validate_json(
            (directory / "continuation.json").read_bytes()
        )
        raw = reused_specification.read_bytes()
        if (
            reused_specification != directory / "frozen-spec.md"
            or record.attempt != attempt
            or record.spec_digest != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("Reused specification must match continuation provenance")
        reused_spec = raw.decode("utf-8")
    if run.outcome == RunOutcome.VERIFIED:
        if attempt is None or candidate is None or test is None:
            raise ValueError("VERIFIED PACKAGE requires complete verification evidence")
        reviews = [s for s in stages if isinstance(s.output.result, ReviewStageResult)]
        designs = [s for s in stages if s.stage.value == "design"]
        if len(reviews) != 1 or (
            len(designs) != 1 if reused_spec is None else bool(designs)
        ):
            raise ValueError("VERIFIED PACKAGE requires DESIGN and REVIEW")
        review = reviews[0].output.result
        assert isinstance(review, ReviewStageResult)
        decision = evaluate_review(
            contract=contract,
            attempt=attempt,
            candidate=candidate,
            test=test,
            specification=reused_spec
            if reused_spec is not None
            else designs[0].output.artifact or "",
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
    # Only the validated dedicated child can be excluded from evidence. Never
    # traverse checkout contents, including repository symlinks and .git links.
    excluded: Path | None = None
    if workspace is not None:
        workspace = validate_workspace_placement(
            path=workspace, run_directory=directory
        )
        selection = load_selection(directory, run.run_id)
        if selection is not None and selection.path != workspace:
            raise ValueError("Workspace differs from admitted execution selection")
        if workspace == directory.resolve() / "workspace":
            if load_layout(directory, run.run_id) is None and selection is None:
                raise ValueError(
                    "Workspace exclusion requires durable layout or selection"
                )
            excluded = directory / "workspace"
    # Inspect before creating any outputs and refuse foreign persisted records.
    _files(directory, excluded)
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
        f"Attempt: `{attempt.attempt_id}`; start: `{attempt.start_sha}`"
        if attempt
        else "Attempt: unavailable",
        "DESIGN: reused frozen specification"
        if reused_spec is not None
        else "DESIGN: fresh invocation",
        f"Workspace: `{workspace}`" if workspace else "Workspace: unknown",
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
    process_reports = [
        stage.output.process_report
        for stage in stages
        if stage.output.process_report is not None
    ]
    lines.extend(["", "## Development process", ""])
    if process_reports:
        lines.append(
            "BUILD records are agent-reported, not trusted TEST receipts. "
            "Historical execution order is not independently verified. "
            "Details: build/build-process.json."
        )
        for process in process_reports:
            lines.extend(
                f"- {check.phase}: reported exit={check.returncode}"
                for check in process.checks
            )
    else:
        lines.append("Unavailable; historical test-first execution is unverified.")
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
    files = _files(directory, excluded)
    evidence = RunEvidence(
        reused_spec_sha256=hashlib.sha256(reused_spec.encode()).hexdigest()
        if reused_spec is not None
        else None,
        workspace=workspace,
        package_timing=Timing(
            stage=ArtifactStage.PACKAGE,
            started_at=package_started_at,
            ended_at=datetime.now(UTC),
            duration_seconds=time.monotonic() - package_start,
            original_seconds=timing.original_seconds,
            remaining_seconds=timing.remaining_seconds,
        ),
        run=run,
        contract=contract,
        attempt=attempt,
        candidate=candidate,
        timing=timing,
        stage_timings=stage_timings,
        stages=stages,
        test=test,
        files=files,
        unverified=tuple(missing),
        error=error,
    )
    with (directory / "evidence.json").open("x", encoding="utf-8") as output:
        output.write(evidence.model_dump_json(indent=2))
    return evidence
