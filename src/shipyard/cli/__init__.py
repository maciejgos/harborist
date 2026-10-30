"""Register the CLI commands; handlers own their presentation and options."""

import typer

from shipyard.cli.apply import apply_command
from shipyard.cli.inspection import inspect, methodology
from shipyard.cli.intake import intake
from shipyard.cli.run import run_command

app = typer.Typer(
    no_args_is_help=True,
    help="Freeze, execute, inspect and explicitly apply verified Shipyard Runs.",
)
app.command()(intake)
app.command()(inspect)
app.command()(methodology)
app.command("run")(run_command)
app.command("apply")(apply_command)
