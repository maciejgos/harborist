"""Append read-only GitHub observations and prepare explicitly selected feedback."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel

from harborist.application.publication import (
    PullRequest,
    latest_publication,
    publication_directory,
)
from harborist.domain.revision import GitCommitSha
from harborist.github.cli import api
from harborist.github.collaboration import (
    CheckPage,
    Feedback,
    StatusPage,
    collect_ci,
    collect_feedback,
    select_feedback,
)
from harborist.persistence import FileRunStore
from harborist.persistence.application import ensure_record_directory, write_new_record


class PullState(PullRequest):
    merged: bool
    merged_at: datetime | None
    merge_commit_sha: GitCommitSha | None


class Observation(BaseModel):
    run_id: UUID
    repository: str
    observed_at: datetime
    pull: int
    url: str
    state: str
    head: GitCommitSha
    verified_candidate: GitCommitSha
    head_verified: bool
    merged_at: datetime | None
    merge_commit_sha: GitCommitSha | None
    checks: CheckPage
    statuses: StatusPage
    feedback: tuple[Feedback, ...]


def observe_pull(root: Path, run_id: UUID) -> tuple[Observation, Path]:
    publication = latest_publication(publication_directory(root, run_id))
    if publication is None or publication.pull is None:
        raise ValueError("Run has no completed GitHub publication")
    repository = publication.repository
    endpoint = f"repos/{repository}/pulls/{publication.pull}"
    pull = PullState.model_validate(api(endpoint))
    if pull.number != publication.pull or pull.head.ref != f"harborist/{run_id}":
        raise ValueError("GitHub response does not match the published PR")
    checks, statuses = collect_ci(repository, pull.head.sha)
    feedback = collect_feedback(repository, pull.number)
    current = PullState.model_validate(api(endpoint))
    if (
        current.number,
        current.head,
        current.state,
        current.merged_at,
        current.merge_commit_sha,
    ) != (pull.number, pull.head, pull.state, pull.merged_at, pull.merge_commit_sha):
        raise ValueError("GitHub PR changed during capture; retry")
    now = datetime.now(UTC)
    observation = Observation(
        run_id=run_id,
        repository=repository,
        observed_at=now,
        pull=pull.number,
        url=pull.html_url,
        state="merged" if pull.merged else pull.state,
        head=pull.head.sha,
        verified_candidate=publication.candidate,
        head_verified=pull.head.sha == publication.candidate,
        merged_at=pull.merged_at,
        merge_commit_sha=pull.merge_commit_sha if pull.merged else None,
        checks=checks,
        statuses=statuses,
        feedback=feedback,
    )
    directory = publication_directory(root, run_id) / "observations"
    ensure_record_directory(directory)
    path = directory / f"{now:%Y%m%dT%H%M%S%f}-{uuid4()}.json"
    write_new_record(path, observation)
    return observation, path


def prepare_feedback(
    root: Path, run_id: UUID, path: Path, keys: tuple[str, ...]
) -> str:
    expected = publication_directory(root, run_id) / "observations"
    if path.resolve().parent != expected.resolve():
        raise ValueError("Select a saved observation for this Run")
    observation = Observation.model_validate_json(path.read_bytes())
    if observation.run_id != run_id:
        raise ValueError("Observation belongs to another Run")
    # Use the locally packaged candidate as the starting revision. Feedback is
    # data for PLAN, and never implicitly imports the remote branch.
    run = FileRunStore(root=root).load_state(run_id)
    if (
        run.verification is None
        or run.verification.candidate.candidate_sha != observation.verified_candidate
    ):
        raise ValueError("Observation belongs to a previous verified candidate")
    selected = select_feedback(observation.feedback, keys)
    if not selected:
        raise ValueError("Select at least one GitHub feedback ID")
    return (
        f"GitHub PR {observation.url} (observed head {observation.head})\n\n{selected}"
    )
