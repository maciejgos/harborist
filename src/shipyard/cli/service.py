"""Operate the local background service without coupling it to a client terminal."""

import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from shipyard.control.client import ControlClient
from shipyard.paths import data_root

service_app = typer.Typer(
    no_args_is_help=True, help="Manage the local execution service."
)
ControlDirectory = Annotated[
    Path | None, typer.Option(help="Service directory (default ~/.shipyard/control).")
]


def control_root(directory: Path | None) -> Path:
    return (directory if directory is not None else data_root() / "control").resolve()


@service_app.command("serve")
def serve(control_dir: ControlDirectory = None) -> None:
    """Run the service in this process (for supervisors and diagnostics)."""
    from shipyard.agents.codex import CodexAgent
    from shipyard.control.queue import QueueStore
    from shipyard.control.service import ControlService

    service = ControlService(QueueStore(control_root(control_dir)), agent=CodexAgent())
    previous = {
        signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)
    }

    def stop(signum: int, frame: object) -> None:
        service.stop()

    try:
        for signum in previous:
            signal.signal(signum, stop)
        service.serve()
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


@service_app.command("start")
def start(control_dir: ControlDirectory = None) -> None:
    """Start detached; wait briefly for readiness, recording diagnostics locally."""
    root = control_root(control_dir)
    client = ControlClient(root)
    try:
        health = client.request("GET", "/health")
    except ValueError:
        pass
    else:
        typer.echo(json.dumps(health))
        return
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    try:
        with (root / "service.log").open("ab") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "shipyard",
                    "service",
                    "serve",
                    "--control-dir",
                    str(root),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                close_fds=True,
            )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                health = client.request("GET", "/health")
            except ValueError:
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            else:
                typer.echo(json.dumps(health))
                return
        raise ValueError(
            f"Service did not become ready; inspect {root / 'service.log'}"
        )
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


@service_app.command("status")
def service_status(control_dir: ControlDirectory = None) -> None:
    _request(control_dir, "GET", "/health")


@service_app.command("stop")
def stop_service(control_dir: ControlDirectory = None) -> None:
    """Request graceful drain; the active Run continues through PACKAGE."""
    _request(control_dir, "POST", "/stop")


def _request(directory: Path | None, method: str, route: str) -> None:
    try:
        typer.echo(
            json.dumps(ControlClient(control_root(directory)).request(method, route))
        )
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
