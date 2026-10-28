"""Capture Shipyard-controlled TEST evidence for one exact candidate."""

from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shipyard.domain import RunContract, VerificationConfigSnapshot
from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.playbook_execution import StageReceipt, StepOutcome
from shipyard.git import GitRepository
from shipyard.git.repository import GitReadError
from shipyard.verification.runner import CheckCollection, run_checks


class TestExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: UUID
    attempt_id: UUID
    verification: VerificationConfigSnapshot
    collection: CheckCollection
    workspace_error: str | None
    receipt: StageReceipt


def execute_test(
    *,
    contract: RunContract,
    attempt: Attempt,
    candidate: Candidate,
    workspace: Path,
    output_dir: Path,
    check_timeout_seconds: float,
    total_timeout_seconds: float | None = None,
    cleanup_workspace: Callable[[], None] | None = None,
) -> TestExecution:
    """Write manifest last; caller owns total budget and lifecycle transitions.

    The Run executor supplies cleanup for its owned isolated workspace. Lower-level
    callers default to retaining residue and failing closed. Source changes always
    fail the exact-revision assertion, independently of check exit status.
    """
    if attempt.run_id != contract.run_id or candidate.attempt_id != attempt.attempt_id:
        raise ValueError("TEST identities must belong to the frozen Run and Attempt")
    workspace = workspace.resolve(strict=True)
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(workspace):
        raise ValueError("TEST evidence must be outside the candidate workspace")
    repository = GitRepository(path=workspace)
    repository.require_clean_revision(commit_sha=candidate.candidate_sha)
    output_dir.mkdir()
    collection = run_checks(
        config=contract.verification.config,
        workspace=workspace,
        logs_dir=output_dir / "logs",
        timeout_seconds=check_timeout_seconds,
        total_timeout_seconds=total_timeout_seconds,
    )
    workspace_error = None
    try:
        if cleanup_workspace is not None:
            cleanup_workspace()
        repository.require_clean_revision(commit_sha=candidate.candidate_sha)
    except GitReadError as error:
        workspace_error = str(error)
    execution = TestExecution(
        run_id=contract.run_id,
        attempt_id=attempt.attempt_id,
        verification=contract.verification,
        collection=collection,
        workspace_error=workspace_error,
        receipt=StageReceipt(
            stage=ArtifactStage.TEST,
            candidate=candidate,
            outcome=StepOutcome.SUCCEEDED
            if collection.passed and workspace_error is None
            else StepOutcome.TEST_FAILED,
        ),
    )
    with (output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(execution.model_dump_json())
    return execution
