"""Launch the local, read-only execution dashboard."""

from pathlib import Path
from typing import Annotated

import typer

from shipyard.cli.service import control_root
from shipyard.web.server import create_server


def web(
    control_dir: Annotated[
        Path | None, typer.Option(help="Existing service control directory.")
    ] = None,
    port: Annotated[
        int, typer.Option(min=1, max=65535, help="Loopback dashboard port.")
    ] = 8765,
) -> None:
    """View execution at http://127.0.0.1:8765; run service start separately.

    Closing the monitor does not stop execution. Restart an older service after
    upgrading Shipyard to expose the new stage history and artifact endpoints.
    """
    try:
        with create_server(control_dir=control_root(control_dir), port=port) as server:
            typer.echo(f"Shipyard monitor: http://127.0.0.1:{server.server_port}")
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    except OSError as error:
        typer.echo(
            f"Cannot start monitor: {error}; select another --port if occupied.",
            err=True,
        )
        raise typer.Exit(1) from error
