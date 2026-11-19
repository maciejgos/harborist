"""Explicit synchronous application; no agent, check execution or Run writes."""

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from harborist.application.context import resolve_context
from harborist.domain.application import ApplicationReceipt
from harborist.evidence.application import load_application_evidence
from harborist.git.repository import GitRepository
from harborist.persistence import FileRunStore
from harborist.persistence.application import ApplicationStore


@dataclass(frozen=True)
class ApplicationResult:
    receipt: ApplicationReceipt
    path: Path
    already_applied: bool


def apply_run(
    *,
    run_id: UUID,
    branch: str,
    repository: Path | None = None,
    runs_dir: Path | None = None,
) -> ApplicationResult:
    repository, root = resolve_context(
        run_id=run_id, repo=repository, runs_dir=runs_dir
    )
    evidence = load_application_evidence(root=root, run_id=run_id)
    assert evidence.candidate is not None
    candidate = evidence.candidate.candidate_sha
    git = GitRepository(path=repository)
    try:
        git.validate_application_candidate(
            run_id=run_id,
            base=evidence.contract.base_sha,
            candidate=candidate,
            attempt_id=evidence.attempt.attempt_id
            if evidence.attempt and FileRunStore(root=root).selected_number(run_id)
            else None,
        )
        previous = git.preflight_application(branch=branch, candidate=candidate)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError(
            f"Cannot apply verified candidate {candidate}: {error}"
        ) from error
    store = ApplicationStore(
        root=root, run_id=run_id, repository=repository, branch=branch
    )
    try:
        with store.reserve():
            existing = store.existing(candidate)
            if existing is not None:
                if git.branch_sha(branch) != candidate:
                    raise ValueError(
                        "Previously applied target has changed; create a new Run against the updated target"
                    )
                return ApplicationResult(existing, store.path, True)
            receipt = ApplicationReceipt(
                run_id=run_id,
                candidate_sha=candidate,
                repository=repository,
                branch=branch,
                previous_sha=previous,
                resulting_sha=candidate,
                timestamp=datetime.now(UTC),
                operation="observed_noop" if previous == candidate else "advanced",
            )
            pending = store.prepare(receipt)
            if previous != candidate:
                if pending.previous_sha != previous:
                    raise ValueError(
                        "Target changed since receipt preparation; inspect pending record and create a new Run"
                    )
                git.advance_branch(
                    branch=branch, previous=previous, candidate=candidate
                )
                store.confirm(receipt)
            else:
                confirmed = store.confirmed(candidate)
                if confirmed is not None:
                    receipt = confirmed
                # Without a durable post-Git confirmation, equality establishes
                # only an observed no-op, never an earlier advancement by us.
            if git.branch_sha(branch) != candidate:
                raise ValueError("Target changed before receipt publication")
            store.publish(receipt)
            if git.branch_sha(branch) != candidate:
                raise ValueError("Target changed after receipt publication")
            return ApplicationResult(receipt, store.path, previous == candidate)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        try:
            observed = git.branch_sha(branch)
        except OSError, ValueError, subprocess.SubprocessError:
            observed = "unavailable"
        raise ValueError(
            f"Application failed for candidate {candidate}: {error}. Observed target SHA: {observed}. "
            f"Receipt: {store.path} (exists={store.path.exists()}); "
            f"preparation: {store.preparation}. Partial Git/receipt state is retained. "
            "Inspect the target and checkout, resolve the reported obstruction, then retry "
            "the same apply command; no rollback or cleanup was performed."
        ) from error
