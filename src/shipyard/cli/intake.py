"""Capture-only CLI command."""

import json
from pathlib import Path
from typing import Annotated

import typer

from shipyard.cli.capture import capture_run, execution_command


def intake(
    source: Annotated[
        str, typer.Argument(help="file:path or github:owner/repo#number")
    ],
    settings: Annotated[
        Path | None,
        typer.Option(
            help="Optional operator YAML override; methodology paths resolve beside it."
        ),
    ] = None,
    repo: Annotated[
        Path, typer.Option(help="Target implementation repository.")
    ] = Path("."),
    ref: Annotated[str, typer.Option(help="Base commit-ish, resolved once.")] = "HEAD",
    runs_dir: Annotated[
        Path | None,
        typer.Option(help="Filesystem Runs root (default: ~/.shipyard/runs)."),
    ] = None,
    timeout: Annotated[
        int, typer.Option(help="Overall execution budget in seconds.", min=1)
    ] = 1800,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print the full frozen contract as JSON.")
    ] = False,
    verification_reserve: Annotated[
        int, typer.Option(help="Seconds reserved for verification.", min=1)
    ] = 300,
) -> None:
    """Capture a CREATED Run and print a human-readable summary.

    Defaults to shipyard.settings.yaml at the target checkout root selected by
    --repo (default: .), including from subdirectories. --settings PATH takes
    precedence; relative explicit paths use the invocation directory.
    Methodology paths resolve beside the selected settings file. On missing or
    invalid settings, supply --settings PATH. No other locations are searched.

    Existing scripts consuming JSON stdout must add --json for the full frozen contract.
    Prints shipyard run <run-id>; custom storage adds only --runs-dir.
    Does not execute agents or verification checks.
    """
    try:
        contract, root, runs_dir = capture_run(
            source=source,
            settings=settings,
            repo=repo,
            ref=ref,
            runs_dir=runs_dir,
            timeout=timeout,
            verification_reserve=verification_reserve,
        )
    except (ValueError, OSError) as error:
        typer.echo(json.dumps({"error": str(error)}), err=True)
        raise typer.Exit(code=1) from error
    command = execution_command(contract.run_id, runs_dir)
    if json_output:
        typer.echo(contract.model_dump_json())
        typer.echo(command, err=True)
    else:
        typer.echo(
            f"Run captured\n"
            f"ID:         {contract.run_id}\n"
            f"Repository: {root}\n"
            f"Base:       {contract.base_sha}\n"
            f"Task:       {contract.intent.source_ref}\n"
            f"Status:     CREATED\n\n"
            f"Execute:\n  {command}"
        )
