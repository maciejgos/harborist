"""Push exact commits with an explicit expected remote ref."""

from pathlib import Path

from shipyard.git.command import run_git


def expected_head(
    *, observed: str | None, previous: str | None, candidate: str
) -> bool:
    if observed == candidate:
        return True
    if observed != previous:
        raise ValueError("GitHub head changed since publication was approved")
    return False


def push_candidate(
    path: Path, url: str, ref: str, candidate: str, previous: str | None
) -> None:
    if previous is not None:
        run_git(path, "merge-base", "--is-ancestor", previous, candidate)
    run_git(
        path,
        "-c",
        "push.followTags=false",
        "push",
        "--no-verify",
        f"--force-with-lease={ref}:{previous or ''}",
        "--",
        url,
        f"{candidate}:{ref}",
    )
