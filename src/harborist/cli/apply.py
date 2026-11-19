"""Explicit verified candidate application command."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer


def apply_command(
    run_id: UUID,
    branch: Annotated[
        str, typer.Option(help="Existing local branch to fast-forward; required.")
    ],
    repo: Annotated[
        Path | None, typer.Option(help="Repository checkout; must match saved context.")
    ] = None,
    runs_dir: Annotated[
        Path | None,
        typer.Option(help="Runs storage locator (default: ~/.harborist/runs)."),
    ] = None,
) -> None:
    """Explicitly apply a packaged VERIFIED candidate without rerunning verification.

    Saved context selects the repository independently of cwd. Only an absent
    locator permits --repo/cwd fallback. Advances require ancestry and a clean
    selected checkout, including ignored files. Other occupied worktrees block
    advancement; unoccupied branches leave checkout files alone. Already-equal
    targets are successful no-ops. Receipts live under applications/<run-id>/ in
    Runs storage. Partial failures retain preparation records: inspect the reported
    target and receipt paths, resolve obstructions, then retry this command.
    """
    import subprocess

    from harborist.application.apply import apply_run

    try:
        result = apply_run(
            run_id=run_id, branch=branch, repository=repo, runs_dir=runs_dir
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        typer.echo(
            f"Application failed for Run {run_id}, branch {branch}: {error}", err=True
        )
        raise typer.Exit(code=1) from error
    typer.echo(
        f"{'Already applied' if result.already_applied else 'Applied'}: Run {run_id}"
    )
    typer.echo(f"Branch: {branch}")
    typer.echo(f"Candidate: {result.receipt.candidate_sha}")
    typer.echo(f"Receipt: {result.path}")
