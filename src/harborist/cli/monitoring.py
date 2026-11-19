"""Reconnectable, read-only views over background delivery records."""

import json
import time
from pathlib import Path
from typing import Annotated, cast
from uuid import UUID

import typer

from harborist.cli.service import control_root
from harborist.control.client import ControlClient

ControlDirectory = Annotated[
    Path | None, typer.Option(help="Background service directory.")
]
JsonOutput = Annotated[
    bool, typer.Option("--json", help="Print the service JSON response.")
]
TERMINAL = {"FINISHED", "FAILED", "INTERRUPTED", "CANCELLED"}


def _fields(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def render_record(record: dict[str, object]) -> str:
    run_id = _fields(record.get("submission")).get("run_id", "unknown")
    lines = [
        f"Run: {run_id}",
        f"Delivery: {record.get('state') or 'Not submitted to service'}",
    ]
    retirement = _fields(record.get("retirement"))
    if retirement:
        replacement = retirement.get("replacement")
        lines.append(f"Disposition: {'SUPERSEDED' if replacement else 'CANCELLED'}")
        lines.append(f"Reason: {retirement.get('reason')}")
        if replacement:
            lines.append(f"Replacement Run: {replacement}")
    run = _fields(record.get("run"))
    for label, key in (
        ("Status", "lifecycle"),
        ("Outcome", "outcome"),
        ("Failure", "failure_reason"),
    ):
        if run.get(key) is not None:
            lines.append(f"{label}: {run[key]}")
    progress = _fields(record.get("progress"))
    if progress:
        lines.append(
            f"Progress: {str(progress.get('stage', 'unknown')).upper()} {progress.get('state', 'unknown')} (observational)"
        )
    if "package_available" in record:
        lines.append(
            "Package: "
            + ("available" if record["package_available"] else "unavailable")
        )
    for name, path in _fields(record.get("artifacts")).items():
        lines.append(f"{name}: {path}")
    for label, key in (("Delivery error", "error"), ("Run unavailable", "run_error")):
        if record.get(key):
            lines.append(f"{label}: {record[key]}")
    return "\n".join(lines)


def status(
    run_id: UUID,
    control_dir: ControlDirectory = None,
    json_output: JsonOutput = False,
    wait: Annotated[
        bool, typer.Option(help="Wait for delivery to become terminal.")
    ] = False,
    interval: Annotated[
        float, typer.Option(min=0.01, max=60, help="Polling seconds.")
    ] = 1,
) -> None:
    """Inspect a saved Run or service submission; leaving this viewer never cancels execution.

    Exit zero means status was read successfully, not that the Run is VERIFIED.
    """
    client = ControlClient(control_root(control_dir))
    try:
        while True:
            record = client.request("GET", f"/runs/{run_id}")
            lifecycle = _fields(record.get("run")).get("lifecycle")
            if (
                not wait
                or record.get("state") in TERMINAL
                or lifecycle in {"COMPLETED", "FAILED", "CANCELLED"}
            ):
                typer.echo(json.dumps(record) if json_output else render_record(record))
                return
            time.sleep(interval)
    except KeyboardInterrupt as error:
        typer.echo("Stopped watching; background execution continues.", err=True)
        raise typer.Exit(130) from error
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


def runs(control_dir: ControlDirectory = None, json_output: JsonOutput = False) -> None:
    """List saved Runs in ~/.harborist/runs plus service submissions."""
    try:
        response = ControlClient(control_root(control_dir)).request("GET", "/runs")
        if json_output:
            typer.echo(json.dumps(response))
        else:
            records = response.get("runs", [])
            if not isinstance(records, list):
                raise ValueError("Invalid Run listing")
            typer.echo(
                "\n\n".join(
                    render_record(record)
                    for record in cast(list[dict[str, object]], records)
                )
                or "No saved Runs."
            )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
