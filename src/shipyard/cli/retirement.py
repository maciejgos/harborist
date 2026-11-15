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


def supersede(
    run_id: UUID,
    source: Annotated[
        str | None, typer.Argument(help="Replacement file: or github: source.")
    ] = None,
    *,
    reason: Annotated[str, typer.Option(help="Why the request is being replaced.")],
    replacement: Annotated[
        UUID | None, typer.Option(help="Retry with a saved replacement Run.")
    ] = None,
    repo: Annotated[Path | None, typer.Option()] = None,
    settings: Annotated[Path | None, typer.Option()] = None,
    ref: Annotated[str, typer.Option()] = "HEAD",
    runs_dir: Annotated[Path | None, typer.Option()] = None,
    control_dir: Annotated[Path | None, typer.Option()] = None,
    timeout: Annotated[int, typer.Option(min=1)] = 1800,
    verification_reserve: Annotated[int, typer.Option(min=1)] = 300,
) -> None:
    """Freeze a replacement request and supersede the original Run."""
    from shipyard.application.capture import capture_run
    from shipyard.application.context import resolve_context
    from shipyard.persistence.retirement import RetirementRequest

    try:
        if (source is None) == (replacement is None):
            raise ValueError(
                "Supply a replacement source or --replacement for a saved capture"
            )
        request = RetirementRequest(reason=reason)
        repository, root = resolve_context(run_id=run_id, repo=repo, runs_dir=runs_dir)
        if source is not None:
            contract, _, _ = capture_run(
                source=source,
                settings=settings,
                repo=repository,
                ref=ref,
                runs_dir=root,
                timeout=timeout,
                verification_reserve=verification_reserve,
            )
            replacement = contract.run_id
            typer.echo(f"Replacement Run: {replacement}")
        ControlClient(control_root(control_dir)).request(
            "POST",
            f"/runs/{run_id}/supersede",
            RetirementRequest(
                reason=request.reason,
                runs_root=root,
                replacement=replacement,
            ).model_dump(mode="json"),
        )
    except (ValueError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Run {run_id} superseded by {replacement}")
