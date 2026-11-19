"""Register the CLI commands; handlers own their presentation and options."""

import typer

from harborist.cli.agent import agent_app
from harborist.cli.apply import apply_command
from harborist.cli.continuation import recover, rework
from harborist.cli.github import github_status, publish
from harborist.cli.inspection import inspect, methodology
from harborist.cli.intake import intake
from harborist.cli.monitoring import runs, status
from harborist.cli.retirement import cancel, supersede
from harborist.cli.run import run_command
from harborist.cli.service import service_app
from harborist.cli.tickets import tickets_app
from harborist.cli.web import web

app = typer.Typer(
    no_args_is_help=True,
    help="Freeze, execute, inspect and explicitly apply verified Harborist Runs.",
)
app.command()(intake)
app.command()(inspect)
app.command()(methodology)
app.command("run")(run_command)
app.command("apply")(apply_command)
app.command()(rework)
app.command()(recover)

app.add_typer(agent_app, name="agent")
app.add_typer(service_app, name="service")
app.add_typer(
    tickets_app, name="tickets", help="Browse GitHub issues and queue a ticket Run."
)

app.command("runs")(runs)
app.command("status")(status)

app.command("web")(web)
app.command()(publish)
app.command()(github_status)
app.command()(cancel)
app.command()(supersede)
