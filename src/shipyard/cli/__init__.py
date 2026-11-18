"""Register the CLI commands; handlers own their presentation and options."""

import typer

from shipyard.cli.agent import agent_app
from shipyard.cli.apply import apply_command
from shipyard.cli.continuation import recover, rework
from shipyard.cli.github import github_status, publish
from shipyard.cli.inspection import inspect, methodology
from shipyard.cli.intake import intake
from shipyard.cli.monitoring import runs, status
from shipyard.cli.retirement import cancel, supersede
from shipyard.cli.run import run_command
from shipyard.cli.service import service_app
from shipyard.cli.tickets import tickets_app
from shipyard.cli.web import web

app = typer.Typer(
    no_args_is_help=True,
    help="Freeze, execute, inspect and explicitly apply verified Shipyard Runs.",
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
