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


def parse_github_selector(source: str) -> tuple[str, str]:
    """Validate a selector without contacting GitHub."""
    match = _SELECTOR.fullmatch(source)
    if match is None:
        raise GitHubIntakeError("Expected github:owner/repo#positive-issue-number")
    return match.group(1), match.group(2)


def read_github_intent(*, run_id: UUID, source: str) -> IntentSnapshot:
    """Capture once; comments and subsequent Issue edits are not inputs."""
    repository, number = parse_github_selector(source)
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
    except FileNotFoundError as error:
        raise GitHubIntakeError(
            f"Cannot capture GitHub issue {source}: install GitHub CLI (gh) "
            "and ensure gh is on PATH."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise GitHubIntakeError(
            f"Cannot capture GitHub issue {source}: gh timed out; retry capture "
            "after checking network connectivity."
        ) from error
    except subprocess.CalledProcessError as error:
        raise GitHubIntakeError(
            f"Cannot capture GitHub issue {source}: gh request failed; run "
            "gh auth login and check access to the selected issue."
        ) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise GitHubIntakeError(
            f"Cannot capture GitHub issue {source}: cannot start gh; check "
            "installation, PATH and executable permissions."
        ) from error
    except ValueError as error:
        raise GitHubIntakeError(
            f"Cannot capture GitHub issue {source}: invalid response; check "
            "GitHub CLI (gh) installation and access to the selected issue."
        ) from error
