"""Publish an explicitly approved, packaged candidate through Git and GitHub."""

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, TypeAdapter

from shipyard.application.context import resolve_context
from shipyard.domain.revision import GitCommitSha
from shipyard.evidence.application import load_application_evidence
from shipyard.git.command import run_git
from shipyard.git.publication import expected_head, push_candidate
from shipyard.git.repository import GitRepository
from shipyard.github.cli import api
from shipyard.persistence import FileRunStore
from shipyard.persistence.application import ensure_record_directory, write_new_record
from shipyard.persistence.continuation import execution_lock
from shipyard.persistence.retirement import require_live_run


class Branch(BaseModel):
    ref: str
    sha: GitCommitSha


class PullRequest(BaseModel):
    number: int
    html_url: str
    state: str
    head: Branch
    base: Branch
    body: str | None


class Publication(BaseModel):
    repository: str
    base: str
    candidate: GitCommitSha
    attempt: UUID
    previous: GitCommitSha | None
    timestamp: datetime
    pull: int | None = None


def find_pull(repository: str, branch: str) -> PullRequest | None:
    owner = repository.split("/")[0]
    pulls = TypeAdapter(list[PullRequest]).validate_python(
        api(f"repos/{repository}/pulls?state=all&head={owner}:{branch}&per_page=2")
    )
    if len(pulls) > 1:
        raise ValueError("Multiple GitHub PRs use the Run branch")
    return pulls[0] if pulls else None


def publication_directory(root: Path, run_id: UUID) -> Path:
    return root / "publications" / str(run_id)


def latest_publication(directory: Path) -> Publication | None:
    paths = sorted(directory.glob("published-*.json"))
    return Publication.model_validate_json(paths[-1].read_bytes()) if paths else None


def publish_run(
    run_id: UUID,
    *,
    approve: str,
    destination: str,
    base: str,
    expect_head: str | None = None,
    runs_dir: Path | None = None,
) -> PullRequest:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", destination):
        raise ValueError("Expected a GitHub destination in owner/repository form")
    repository, root = resolve_context(run_id=run_id, repo=None, runs_dir=runs_dir)
    store = FileRunStore(root=root)
    with execution_lock(store, run_id):
        require_live_run(root, run_id)
        evidence = load_application_evidence(root=root, run_id=run_id)
        assert evidence.candidate and evidence.attempt and evidence.test
        candidate = evidence.candidate.candidate_sha
        attempt = evidence.attempt.attempt_id
        if candidate != approve:
            raise ValueError("Approval must match the full VERIFIED candidate SHA")
        GitRepository(path=repository).validate_application_candidate(
            run_id=run_id,
            base=evidence.contract.base_sha,
            candidate=candidate,
            attempt_id=attempt if store.selected_number(run_id) else None,
        )
        run_git(repository, "check-ref-format", f"refs/heads/{base}")
        branch = f"shipyard/{run_id}"
        if base == branch:
            raise ValueError("PR base must differ from the Shipyard branch")
        ref = f"refs/heads/{branch}"
        url = f"https://github.com/{destination}.git"
        directory = publication_directory(root, run_id)
        ensure_record_directory(directory)
        prior = latest_publication(directory)
        pending_path = directory / f"prepared-{attempt}.json"
        pending = (
            Publication.model_validate_json(pending_path.read_bytes())
            if pending_path.exists()
            else None
        )
        if prior and (prior.repository, prior.base) != (destination, base):
            raise ValueError("Destination differs from the existing Run publication")
        previous = prior.candidate if prior else None
        if prior and prior.attempt == attempt and pending:
            previous = pending.previous
        if expect_head != previous:
            raise ValueError("Expected head must match the previous publication")
        if pending and (
            pending.attempt,
            pending.repository,
            pending.base,
            pending.candidate,
            pending.previous,
        ) != (attempt, destination, base, candidate, previous):
            raise ValueError("Approval conflicts with prepared publication")
        pull = find_pull(destination, branch)
        remote = (
            run_git(repository, "ls-remote", "--refs", "--", url, ref).decode().split()
        )
        observed = remote[0] if remote else None
        if prior and pull is None:
            raise ValueError("Previously published GitHub PR is unavailable")
        if pull and (
            pull.state != "open"
            or pull.base.ref != base
            or pull.head.ref != branch
            or pull.head.sha != observed
            or (prior is not None and pull.number != prior.pull)
            or (prior is None and pending is None)
        ):
            raise ValueError("GitHub PR changed or is not owned by this publication")
        base_head = run_git(
            repository, "ls-remote", "--refs", "--", url, f"refs/heads/{base}"
        )
        if not base_head:
            raise ValueError("GitHub base branch does not exist")
        already_pushed = expected_head(
            observed=observed, previous=previous, candidate=candidate
        )
        if already_pushed and pending is None:
            raise ValueError(
                "GitHub head already exists without a prepared publication"
            )
        if pending is None:
            pending = Publication(
                repository=destination,
                base=base,
                candidate=candidate,
                attempt=attempt,
                previous=previous,
                timestamp=datetime.now(UTC),
            )
            write_new_record(pending_path, pending)
        if prior and prior.attempt == attempt and pull:
            if not already_pushed:
                raise ValueError("GitHub head changed after the completed publication")
            return pull
        if not already_pushed:
            push_candidate(repository, url, ref, candidate, previous)
        summary = (
            run_git(repository, "show", "-s", "--format=%B", candidate).decode().strip()
        )
        review = next(
            stage.output.artifact
            for stage in evidence.stages
            if stage.stage.value == "review"
        )
        limitations = (
            "\n".join(evidence.unverified)[:4000] or "No unverified areas recorded."
        )
        checks = "\n".join(
            f"- {check.id}: {'passed' if check.passed else 'failed'}"
            for check in evidence.test.collection.checks[:128]
        )[:6000]
        body = (
            f"<!-- shipyard-publication:{attempt} -->\n\n"
            f"## Request\n\n{evidence.contract.intent.markdown[:8000]}\n\n"
            f"## Implementation\n\n{summary[:4000]}\n\n"
            f"Base: `{evidence.contract.base_sha}`\n\nCandidate: `{candidate}`\n\n"
            f"## TEST\n\n{checks}\n\n## REVIEW\n\n{(review or '')[:8000]}\n\n"
            f"## Limitations\n\n{limitations}\n\n"
            f"Full local evidence: Run `{run_id}`, Attempt `{attempt}` (`evidence.json`)."
        )
        if pull is None:
            pull = PullRequest.model_validate(
                api(
                    f"repos/{destination}/pulls",
                    payload={
                        "title": f"Shipyard Run {run_id}",
                        "base": base,
                        "head": branch,
                        "body": body,
                    },
                )
            )
        elif previous is not None:
            # Append evidence without overwriting human-authored PR metadata.
            current = find_pull(destination, branch)
            if (
                current is None
                or current.number != pull.number
                or current.head.sha != candidate
                or current.state != "open"
            ):
                raise ValueError("GitHub PR head changed after the branch update")
            api(
                f"repos/{destination}/issues/{pull.number}/comments",
                payload={"body": body},
            )
            pull = current
        if pull.head.sha != candidate or pull.state != "open":
            raise ValueError("GitHub PR does not show the approved candidate")
        receipt = pending.model_copy(update={"pull": pull.number})
        write_new_record(
            directory / f"published-{store.selected_number(run_id):06d}.json", receipt
        )
        return pull
