"""Browse source tickets and explicitly queue one against a saved Workspace."""

from typing import Annotated
from uuid import UUID, uuid4

import typer
from pydantic import TypeAdapter

from shipyard.cli.service import ControlDirectory, control_root
from shipyard.control.client import ControlClient
from shipyard.github.issues import Ticket

tickets_app = typer.Typer(no_args_is_help=True)
_tickets = TypeAdapter(list[Ticket])


@tickets_app.command("list")
@tickets_app.command("refresh")
def list_issues(
    repository: Annotated[str, typer.Argument(help="GitHub source as owner/repo.")],
    control_dir: ControlDirectory = None,
) -> None:
    """Fetch up to 100 open issues from GitHub through the local service."""
    try:
        result = ControlClient(control_root(control_dir)).request(
            "POST", "/tickets/list", {"repository": repository}, timeout=180
        )
        issues = _tickets.validate_python(result.get("issues"))
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    if not issues:
        typer.echo(f"No open issues in {repository}.")
    for issue in issues:
        labels = ", ".join(issue.labels) or "none"
        typer.echo(f"{issue.identity}\t{issue.title}\tLabels: {labels}")


@tickets_app.command("queue")
def queue_issue(
    source: Annotated[str, typer.Argument(help="GitHub issue as owner/repo#number.")],
    workspace: Annotated[UUID, typer.Option(help="Saved target Workspace ID.")],
    control_dir: ControlDirectory = None,
    request_id: Annotated[
        UUID | None,
        typer.Option(help="Reuse a request UUID after an uncertain response."),
    ] = None,
) -> None:
    """Capture the current issue and queue a Run for the target Workspace."""
    request_id = request_id or uuid4()
    try:
        result = ControlClient(control_root(control_dir)).request(
            "POST",
            "/tickets/queue",
            {
                "request_id": str(request_id),
                "source": source,
                "workspace_id": str(workspace),
            },
            timeout=180,
        )
        if result.get("run_id") != str(request_id):
            raise ValueError("Invalid Run identity returned by the local service")
    except ValueError as error:
        typer.echo(f"{error}\nRequest ID: {request_id}", err=True)
        raise typer.Exit(1) from error
    typer.echo(str(request_id))
