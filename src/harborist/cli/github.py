"""Explicit GitHub publication commands."""

import subprocess
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from harborist.application.publication import publish_run


def publish(
    run_id: UUID,
    approve: Annotated[
        str, typer.Option(help="Full VERIFIED candidate SHA to approve.")
    ],
    destination: Annotated[str, typer.Option(help="GitHub owner/repository.")],
    base: Annotated[str, typer.Option(help="Existing GitHub base branch.")],
    expect_head: Annotated[
        str | None, typer.Option(help="Previously published head SHA.")
    ] = None,
    runs_dir: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Publish an explicitly approved candidate to a GitHub PR."""
    try:
        pull = publish_run(
            run_id,
            approve=approve,
            destination=destination,
            base=base,
            expect_head=expect_head,
            runs_dir=runs_dir,
        )
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        typer.echo(f"Publication failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(pull.html_url)


def github_status(
    run_id: UUID,
    runs_dir: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Capture a published PR's current GitHub evidence."""
    from harborist.application.collaboration import observe_pull
    from harborist.application.context import resolve_context

    try:
        _, root = resolve_context(run_id=run_id, repo=None, runs_dir=runs_dir)
        observation, path = observe_pull(root, run_id)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        typer.echo(f"GitHub evidence capture failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(observation.model_dump_json(indent=2))
    typer.echo(f"Observation: {path}", err=True)
