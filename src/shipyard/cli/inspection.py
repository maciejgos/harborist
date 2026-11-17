"""Read-only saved contract and methodology commands."""

import json
from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import typer

from shipyard.domain import ArtifactStage
from shipyard.intake.github import ticket_url
from shipyard.paths import runs_root
from shipyard.persistence import FileRunStore
from shipyard.skills import compile_methodology, compose_guidance


def _fail(error: ValueError) -> NoReturn:
    typer.echo(json.dumps({"error": str(error)}), err=True)
    raise typer.Exit(code=1)


def inspect(
    run_id: UUID,
    runs_dir: Annotated[
        Path | None,
        typer.Option(help="Filesystem Runs root (default: ~/.shipyard/runs)."),
    ] = None,
) -> None:
    """Validate and print a saved contract without reading its original inputs."""
    try:
        contract = FileRunStore(
            root=runs_dir if runs_dir is not None else runs_root()
        ).load(run_id)
    except ValueError as error:
        _fail(error)
    output = contract.model_dump(mode="json")
    if contract.intent.source_url is None and (url := ticket_url(contract.intent)):
        output["intent"]["source_url"] = url
    typer.echo(json.dumps(output))


def methodology(
    run_id: UUID,
    runs_dir: Annotated[
        Path | None,
        typer.Option(help="Filesystem Runs root (default: ~/.shipyard/runs)."),
    ] = None,
    stage: Annotated[
        ArtifactStage | None,
        typer.Option(help="Preview guidance for one native-agent stage."),
    ] = None,
) -> None:
    """Preview saved methodology; does not execute or modify the Run."""
    try:
        contract = FileRunStore(
            root=runs_dir if runs_dir is not None else runs_root()
        ).load(run_id)
        compiled = compile_methodology(contract.execution)
        if stage is not None:
            output = compose_guidance(compiled, stage=stage).model_dump_json()
        else:
            output = json.dumps(
                {
                    "playbook": {
                        "identity": compiled.playbook.identity.model_dump(mode="json"),
                        "definition": compiled.playbook.definition.model_dump(
                            mode="json"
                        ),
                        "guidance": compiled.playbook.guidance,
                    },
                    "skills": [
                        {
                            "identity": skill.identity.model_dump(mode="json"),
                            "metadata": skill.metadata.model_dump(mode="json"),
                            "guidance": skill.guidance,
                        }
                        for skill in compiled.skills
                    ],
                }
            )
    except ValueError as error:
        _fail(error)
    typer.echo(output)
