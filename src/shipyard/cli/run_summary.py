"""Bounded terminal presentation of packaged Run evidence."""

from pathlib import Path

from shipyard.application.review import evaluate_review, validate_test_context
from shipyard.domain.stage_result import (
    AgentStage,
    ReviewStageResult,
    StageStatus,
)
from shipyard.evidence.package import RunEvidence
from shipyard.review.criteria import extract_criteria


def single_line(text: str) -> str:
    """Keep paths and diagnostics readable in redirected terminal output."""
    return "".join(c if c.isprintable() else " " for c in text)


def artifact_paths(directory: Path) -> dict[str, Path]:
    """Called only after PACKAGE returns; never advertise absent outputs."""
    return {
        label: path.resolve()
        for label, name in (("Report", "report.md"), ("Evidence", "evidence.json"))
        if (path := directory / name).is_file() and not path.is_symlink()
    }


def _checks(evidence: RunEvidence) -> str:
    total = len(evidence.contract.verification.config.checks)
    if evidence.test is not None and evidence.attempt and evidence.candidate:
        try:
            validate_test_context(
                contract=evidence.contract,
                attempt=evidence.attempt,
                candidate=evidence.candidate,
                test=evidence.test,
            )
        except ValueError:
            pass
        else:
            passed = sum(check.passed for check in evidence.test.collection.checks)
            return f"{passed}/{total} passed"
    return f"unavailable ({total} required)"


def _acceptance(evidence: RunEvidence) -> str:
    designs = [
        stage
        for stage in evidence.stages
        if stage.stage == AgentStage.DESIGN
        and stage.output.result.status == StageStatus.READY
    ]
    specification = designs[0].output.artifact if len(designs) == 1 else None
    if specification is None:
        return "unavailable (total unknown)"
    try:
        spec = extract_criteria(specification)
    except ValueError:
        return "unavailable (total unknown)"
    unavailable = f"unavailable ({len(spec.criterion_ids)} required)"
    reviews = [stage for stage in evidence.stages if stage.stage == AgentStage.REVIEW]
    if len(reviews) != 1 or not (
        evidence.attempt and evidence.candidate and evidence.test
    ):
        return unavailable
    stage = reviews[0]
    review = stage.output.result
    if not isinstance(review, ReviewStageResult) or stage.review_decision is None:
        return unavailable
    try:
        decision = evaluate_review(
            contract=evidence.contract,
            attempt=evidence.attempt,
            candidate=evidence.candidate,
            specification=specification,
            review=review,
            test=evidence.test,
        )
    except ValueError:
        return unavailable
    if decision != stage.review_decision or decision.specification != spec:
        return unavailable
    return f"{review.summary.pass_count}/{len(spec.criterion_ids)} passed"


def render_summary(evidence: RunEvidence, directory: Path) -> str:
    run = evidence.run
    result = (
        f"Failure: {run.failure_reason}"
        if run.failure_reason
        else f"Result: {run.outcome or run.lifecycle}"
    )
    lines = [
        f"Run {run.lifecycle.value.lower()}",
        f"ID: {run.run_id}",
        f"Status: {run.lifecycle}",
        result,
        f"Candidate: {evidence.candidate.candidate_sha}"
        if evidence.candidate
        else "Candidate: unavailable",
        f"Checks: {_checks(evidence)}",
        f"Acceptance: {_acceptance(evidence)}",
        "Application: This execution has not applied a candidate to the target branch",
        "",
        *[f"{label}: {path}" for label, path in artifact_paths(directory).items()],
    ]
    return "\n".join(single_line(line) for line in lines)
