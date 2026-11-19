"""Inspect the local Codex connection and configure future Run captures."""

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from harborist.agents.codex import CodexAgent
from harborist.configuration.execution import (
    CodexProfileSetup,
    SettingsError,
    codex_profile_status,
    configure_codex_profile,
    execution_settings_path,
)
from harborist.git import GitRepository

agent_app = typer.Typer(no_args_is_help=True, help="Check and configure local Codex.")


def _settings_path(repo: Path, settings: Path | None) -> Path:
    if settings is not None:
        return settings
    return execution_settings_path(GitRepository(path=repo).checkout_root(), None)


@agent_app.command()
def check(
    repo: Annotated[Path, typer.Option(help="Target Git checkout.")] = Path("."),
    settings: Annotated[
        Path | None, typer.Option(help="Operator settings file override.")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Check Codex login in this terminal and validate the selected profile."""
    connection = CodexAgent().check_connection()
    try:
        profile = codex_profile_status(_settings_path(repo, settings))
    except ValueError, OSError:
        profile = {
            "status": "settings_unavailable",
            "message": "Select a Git checkout with --repo or a settings file with --settings.",
        }
    if json_output:
        typer.echo(json.dumps({"connection": connection, "profile": profile}))
    else:
        typer.echo(connection["message"])
        typer.echo(profile["message"])
        if profile["status"] == "configured":
            typer.echo(
                f"Model {profile['model']} · reasoning effort {profile['effort'] or 'Codex default'}"
            )
    if connection["status"] != "ready" or profile["status"] != "configured":
        raise typer.Exit(code=1)


@agent_app.command()
def configure(
    model: Annotated[str, typer.Option(help="Codex model identifier.")],
    effort: Annotated[
        str | None,
        typer.Option(
            help="minimal, low, medium, high, or xhigh. Omit for the Codex default."
        ),
    ] = None,
    repo: Annotated[Path, typer.Option(help="Target Git checkout.")] = Path("."),
    settings: Annotated[
        Path | None, typer.Option(help="Operator settings file override.")
    ] = None,
) -> None:
    """Save the Codex profile in the selected execution settings file."""
    try:
        setup = CodexProfileSetup.model_validate({"model": model, "effort": effort})
    except ValidationError as error:
        typer.echo(
            "Enter a valid Codex model identifier and supported reasoning effort.",
            err=True,
        )
        raise typer.Exit(code=1) from error
    try:
        path = _settings_path(repo, settings)
        configure_codex_profile(path, setup)
    except SettingsError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    except (ValueError, OSError) as error:
        typer.echo(
            "Select a Git checkout with --repo or a settings file with --settings.",
            err=True,
        )
        raise typer.Exit(code=1) from error
    typer.echo(f"Saved the Codex profile in {path} for future Runs.")
