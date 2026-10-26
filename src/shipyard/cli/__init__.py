"""CLI presentation for capture and inspection; workflow execution comes later."""

import json
from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import typer

from shipyard.application import create_run
from shipyard.configuration import load_execution_settings
from shipyard.domain import ExecutionBudget
from shipyard.git import GitRepository
from shipyard.persistence import FileRunStore

app = typer.Typer(
    no_args_is_help=True, help="Freeze and inspect Shipyard Run contracts."
)
_DEFAULT_RUNS = Path.home() / ".shipyard" / "runs"


def _fail(error: ValueError) -> NoReturn:
    typer.echo(json.dumps({"error": str(error)}), err=True)
    raise typer.Exit(code=1)


@app.command()
def intake(
    source: Annotated[
        str, typer.Argument(help="file:path or github:owner/repo#number")
    ],
    settings: Annotated[
        Path,
        typer.Option(
            help="Operator settings YAML; methodology paths resolve beside it."
        ),
    ],
    repo: Annotated[
        Path, typer.Option(help="Target implementation repository.")
    ] = Path("."),
    ref: Annotated[str, typer.Option(help="Base commit-ish, resolved once.")] = "HEAD",
    runs_dir: Annotated[
        Path, typer.Option(help="Filesystem Runs root.")
    ] = _DEFAULT_RUNS,
    timeout: Annotated[
        int, typer.Option(help="Overall execution budget in seconds.", min=1)
    ] = 1800,
    verification_reserve: Annotated[
        int, typer.Option(help="Seconds reserved for verification.", min=1)
    ] = 300,
) -> None:
    """Capture a CREATED Run. Does not execute agents or verification checks."""
    try:
        execution = load_execution_settings(
            path=settings,
            budget=ExecutionBudget(
                total_seconds=timeout, verification_reserve_seconds=verification_reserve
            ),
        )
        contract = create_run(
            source=source,
            repository=GitRepository(path=repo),
            store=FileRunStore(root=runs_dir),
            execution=execution,
            ref=ref,
        )
    except ValueError as error:
        _fail(error)
    typer.echo(contract.model_dump_json())


@app.command()
def inspect(
    run_id: UUID,
    runs_dir: Annotated[
        Path, typer.Option(help="Filesystem Runs root.")
    ] = _DEFAULT_RUNS,
) -> None:
    """Validate and print a saved contract without reading its original inputs."""
    try:
        contract = FileRunStore(root=runs_dir).load(run_id)
    except ValueError as error:
        _fail(error)
    typer.echo(contract.model_dump_json())
