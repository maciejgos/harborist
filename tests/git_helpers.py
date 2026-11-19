"""Real Git helpers with deterministic test-local identity and configuration."""

import os
import subprocess
from pathlib import Path


def git(path: Path, *args: str) -> str:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=Harborist Tests",
            "-c",
            "user.email=tests@harborist.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgSign=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            *args,
        ],
        check=True,
        capture_output=True,
        env=environment,
    )
    return result.stdout.decode("ascii").strip()


def init_repository(path: Path, *, object_format: str = "sha1") -> None:
    path.mkdir()
    git(path, "init", "--initial-branch=main", f"--object-format={object_format}")
