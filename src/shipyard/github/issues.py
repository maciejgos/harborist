"""Read GitHub issues through the local authenticated gh CLI."""

import os
import re
import subprocess
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

GITHUB_REPOSITORY = r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+"
ISSUE_LIMIT = 100
_SELECTOR = re.compile(rf"github:({GITHUB_REPOSITORY})#([1-9][0-9]*)")
type _Text = Annotated[str, StringConstraints(strict=True)]


class GitHubIntakeError(ValueError):
    """A GitHub selector or authoritative issue response could not be read."""


class _Label(BaseModel):
    # gh labels may contain transport metadata beyond the authoritative name.
    model_config = ConfigDict(extra="ignore")
    name: _Text


class _IssueFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: _Text
    labels: tuple[_Label, ...]
    url: _Text

    def label_names(self) -> list[str]:
        return sorted({label.name for label in self.labels})


class Issue(_IssueFields):
    body: _Text


class _ListedIssue(_IssueFields):
    number: int = Field(strict=True, gt=0)


class Ticket(BaseModel):
    identity: str
    title: str
    labels: list[str]
    url: str


_LISTED_ISSUES = TypeAdapter(
    Annotated[list[_ListedIssue], Field(max_length=ISSUE_LIMIT)]
)


def parse_github_selector(source: str) -> tuple[str, str]:
    """Validate a selector without contacting GitHub."""
    match = _SELECTOR.fullmatch(source)
    if match is None or match[1].split("/")[1] in (".", ".."):
        raise GitHubIntakeError("Expected github:owner/repo#positive-issue-number")
    return match[1], match[2]


def issue_url(repository: str, number: str) -> str:
    return f"https://github.com/{repository}/issues/{number}"


def validate_issue_url(url: str, repository: str, number: str) -> str:
    if not url.isascii() or url.lower() != issue_url(repository, number).lower():
        raise ValueError("GitHub issue URL differs from the selected issue")
    return url


def _gh(context: str, *arguments: str) -> bytes:
    try:
        return subprocess.run(
            ["gh", "issue", *arguments],
            check=True,
            capture_output=True,
            timeout=30,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
        ).stdout
    except FileNotFoundError as error:
        raise GitHubIntakeError(
            f"{context}: install GitHub CLI (gh), ensure it is on PATH, and try again."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise GitHubIntakeError(
            f"{context}: GitHub CLI timed out. Check network connectivity and retry."
        ) from error
    except subprocess.CalledProcessError as error:
        raise GitHubIntakeError(
            f"{context}: GitHub request failed. Run gh auth login and check access to the "
            "selected repository or issue."
        ) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise GitHubIntakeError(
            f"{context}: cannot start GitHub CLI (gh). Check installation, PATH and permissions."
        ) from error


def list_tickets(repository: str) -> list[Ticket]:
    """Fetch a fresh list of up to 100 open issues for the explicit repository."""
    if not re.fullmatch(GITHUB_REPOSITORY, repository) or repository.split("/")[1] in (
        ".",
        "..",
    ):
        raise GitHubIntakeError("Source repository: enter owner/repo")
    raw = _gh(
        f"Cannot list issues in {repository}",
        "list",
        "--repo",
        repository,
        "--state",
        "open",
        "--limit",
        str(ISSUE_LIMIT),
        "--json",
        "number,title,labels,url",
    )
    try:
        issues = _LISTED_ISSUES.validate_json(raw)
        return [
            Ticket(
                identity=f"{repository}#{issue.number}",
                title=issue.title,
                labels=issue.label_names(),
                url=validate_issue_url(issue.url, repository, str(issue.number)),
            )
            for issue in issues
        ]
    except ValueError as error:
        raise GitHubIntakeError(
            "GitHub CLI returned an invalid issue list. Check the repository and "
            "GitHub CLI installation, then retry."
        ) from error


def get_issue(repository: str, number: str) -> Issue:
    context = f"Cannot capture GitHub issue github:{repository}#{number}"
    raw = _gh(
        context, "view", number, "--repo", repository, "--json", "title,body,labels,url"
    )
    try:
        issue = Issue.model_validate_json(raw)
        validate_issue_url(issue.url, repository, number)
        return issue
    except ValueError as error:
        raise GitHubIntakeError(
            f"{context}: invalid response; check GitHub CLI (gh) installation "
            "and access to the selected issue."
        ) from error
