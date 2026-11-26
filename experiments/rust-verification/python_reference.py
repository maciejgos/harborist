"""Thin adapter over the existing Harborist verification code."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from harborist.verification.config import parse_verification_config
from harborist.verification.runner import run_checks


def main() -> None:
    repo, base, candidate, workspace, logs = sys.argv[1:]

    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, check=True
        ).stdout

    if git("rev-parse", f"{candidate}^{{commit}}").decode().strip() != candidate:
        raise ValueError("expected the exact candidate commit SHA")
    source = git("show", f"{base}:harborist.yaml")
    config = parse_verification_config(source)
    git("worktree", "add", "--detach", workspace, candidate)
    try:
        checks = run_checks(
            config=config, workspace=Path(workspace), logs_dir=Path(logs),
            timeout_seconds=2, total_timeout_seconds=15, max_log_bytes=65536,
        )
        print(json.dumps({
            "candidate": candidate,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "passed": checks.passed,
            "checks": [item.model_dump(mode="json") for item in checks.checks],
        }))
    finally:
        git("worktree", "remove", "--force", workspace)


if __name__ == "__main__":
    main()
