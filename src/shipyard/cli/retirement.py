"""Explicit local Run disposition commands."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from shipyard.cli.service import control_root
from shipyard.control.client import ControlClient


def cancel(
    run_id: UUID,
    reason: Annotated[str, typer.Option(help="Why the Run is being cancelled.")],
    runs_dir: Annotated[Path | None, typer.Option()] = None,
    control_dir: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Cancel a Run through the local service."""
    try:
        ControlClient(control_root(control_dir)).request(
            "POST",
            f"/runs/{run_id}/cancel",
            {
                "reason": reason,
                "runs_root": str(runs_dir.resolve()) if runs_dir else None,
            },
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Cancellation recorded for Run {run_id}")
