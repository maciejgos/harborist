"""Read authoritative issue fields through the developer's authenticated gh CLI."""

import json
import re
import subprocess
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from shipyard.domain import IntentSnapshot

_SELECTOR = re.compile(
    r"github:([A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+)#([1-9][0-9]*)\Z"
)
type _Text = Annotated[str, StringConstraints(strict=True)]


class GitHubIntakeError(ValueError):
    """A GitHub selector or authoritative issue response could not be captured."""


class _Label(BaseModel):
    # gh labels may contain transport metadata beyond the authoritative name.
    model_config = ConfigDict(extra="ignore")
    name: _Text


class _Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: _Text
    body: _Text
    labels: tuple[_Label, ...]


def read_github_intent(*, run_id: UUID, source: str) -> IntentSnapshot:
    """Capture once; comments and subsequent Issue edits are not inputs."""
    match = _SELECTOR.fullmatch(source)
    if match is None:
        raise GitHubIntakeError("Expected github:owner/repo#positive-issue-number")
    repository, number = match.groups()
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                number,
                "--repo",
                repository,
                "--json",
                "title,body,labels",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        issue = _Issue.model_validate_json(result.stdout)
        labels = json.dumps(
            sorted({label.name for label in issue.labels}), ensure_ascii=False
        )
        markdown = f"# {issue.title}\n\nLabels: {labels}\n\n{issue.body}"
        return IntentSnapshot.create(
            run_id=run_id, source_ref=source, markdown=markdown
        )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise GitHubIntakeError(f"Cannot capture GitHub issue {source}") from error
