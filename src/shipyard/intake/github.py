"""Capture one authoritative GitHub issue as a frozen intent."""

import json
from uuid import UUID

from shipyard.domain import IntentSnapshot
from shipyard.github.issues import (
    get_issue,
    issue_url,
    parse_github_selector,
    validate_canonical_issue_url,
)


def read_github_intent(*, run_id: UUID, source: str) -> IntentSnapshot:
    """Capture once; comments and subsequent Issue edits are not inputs."""
    repository, number = parse_github_selector(source)
    issue = get_issue(repository, number)
    labels = json.dumps(issue.label_names(), ensure_ascii=False)
    return IntentSnapshot.create(
        run_id=run_id,
        source_ref=source,
        source_url=issue.url,
        markdown=f"# {issue.title}\n\nLabels: {labels}\n\n{issue.body}",
    )


def ticket_url(snapshot: IntentSnapshot) -> str | None:
    """Read the saved ticket URL or derive it for captures predating URL storage."""
    try:
        repository, number = parse_github_selector(snapshot.source_ref)
        if snapshot.source_url is None:
            return issue_url(repository, number)
        return validate_canonical_issue_url(snapshot.source_url, number)
    except ValueError:
        return None
