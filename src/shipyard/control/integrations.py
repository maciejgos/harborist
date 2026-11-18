"""Check the existing GitHub CLI connection without reading credentials."""

import os
import re
import subprocess
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shipyard.github.issues import GITHUB_REPOSITORY

CODEX_PROFILE_ROUTE = re.compile(r"/integrations/codex/profile/([0-9a-f-]{36})")


class GitHubCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID | None = None


def check_github(repository: str | None) -> dict[str, object]:
    if repository and not re.fullmatch(GITHUB_REPOSITORY, repository):
        raise ValueError("Invalid GitHub repository")

    def run(*args: str) -> bool:
        return (
            subprocess.run(
                ["gh", *args],
                capture_output=True,
                check=False,
                timeout=8,
                env={**os.environ, "GH_PROMPT_DISABLED": "1"},
            ).returncode
            == 0
        )

    try:
        if not run("auth", "status", "--hostname", "github.com"):
            return {
                "status": "login_required",
                "message": "Run gh auth login --hostname github.com in your terminal, then check again.",
            }
        if repository and not run(
            "api", "--hostname", "github.com", f"repos/{repository}"
        ):
            return {
                "status": "repository_unavailable",
                "message": f"GitHub could not confirm access to {repository}. Check the Workspace repository and your GitHub account’s access.",
            }
    except FileNotFoundError:
        return {
            "status": "cli_missing",
            "message": "Install GitHub CLI (gh), then restart the Shipyard service and check again.",
        }
    except OSError, subprocess.TimeoutExpired:
        return {
            "status": "check_failed",
            "message": "GitHub CLI could not complete the check. Check your connection and try again.",
        }
    return {
        "status": "connected",
        "message": f"GitHub CLI can access {repository}."
        if repository
        else "GitHub CLI is signed in to github.com.",
    }
