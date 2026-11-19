"""Launch the local web workspace."""

from pathlib import Path
from typing import Annotated

import typer

from harborist.cli.service import control_root
from harborist.web.server import create_server


def web(
    control_dir: Annotated[
        Path | None, typer.Option(help="Existing service control directory.")
    ] = None,
    port: Annotated[int, typer.Option(min=1, max=65535, help="Dashboard port.")] = 8765,
    container_listener: Annotated[
        bool,
        typer.Option(
            help="Listen on container interfaces for loopback port publishing."
        ),
    ] = False,
) -> None:
    """Operate Harborist at http://127.0.0.1:8765; run service start separately.

    Closing the monitor does not stop execution. Restart an older service after
    upgrading Harborist to expose the new stage history and artifact endpoints.
    """
    try:
        with create_server(
            control_dir=control_root(control_dir),
            port=port,
            container_listener=container_listener,
        ) as server:
            typer.echo(f"Harborist workspace: http://127.0.0.1:{server.server_port}")
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    except OSError as error:
        typer.echo(
            f"Cannot start workspace: {error}; select another --port if occupied.",
            err=True,
        )
        raise typer.Exit(1) from error
