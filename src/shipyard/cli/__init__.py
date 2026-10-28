"""CLI presentation for frozen capture, synchronous execution and inspection."""

import json
import shlex
from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import typer

from shipyard.application import create_run
from shipyard.application.context import ExecutionContext, load_context
from shipyard.configuration import load_execution_settings
from shipyard.domain import ArtifactStage, ExecutionBudget
from shipyard.git import GitRepository
from shipyard.persistence import FileRunStore
from shipyard.skills import compile_methodology, compose_guidance

app = typer.Typer(
    no_args_is_help=True, help="Freeze, execute and inspect Shipyard Runs."
)
_DEFAULT_RUNS = Path.home() / ".shipyard" / "runs"


def _fail(error: ValueError) -> NoReturn:
    typer.echo(json.dumps({"error": str(error)}), err=True)
    raise typer.Exit(code=1)


@app.command()
def intake(
    source: Annotated[
        str, typer.Argument(help="file:path or github:owner/repo#number")
    ],
    settings: Annotated[
        Path,
        typer.Option(
            help="Operator settings YAML; methodology paths resolve beside it."
        ),
    ],
    repo: Annotated[
        Path, typer.Option(help="Target implementation repository.")
    ] = Path("."),
    ref: Annotated[str, typer.Option(help="Base commit-ish, resolved once.")] = "HEAD",
    runs_dir: Annotated[
        Path, typer.Option(help="Filesystem Runs root.")
    ] = _DEFAULT_RUNS,
    timeout: Annotated[
        int, typer.Option(help="Overall execution budget in seconds.", min=1)
    ] = 1800,
    verification_reserve: Annotated[
        int, typer.Option(help="Seconds reserved for verification.", min=1)
    ] = 300,
) -> None:
    """Capture a CREATED Run. Does not execute agents or verification checks."""
    try:
        execution = load_execution_settings(
            path=settings,
            budget=ExecutionBudget(
                total_seconds=timeout, verification_reserve_seconds=verification_reserve
            ),
        )
        repository = GitRepository(path=repo)
        root = repository.checkout_root()
        runs_dir = runs_dir.resolve()
        contract = create_run(
            source=source,
            repository=GitRepository(path=root),
            store=FileRunStore(root=runs_dir),
            execution=execution,
            ref=ref,
        )
        context = ExecutionContext(
            version=1, run_id=contract.run_id, repository=root, runs_root=runs_dir
        ).save()
    except (ValueError, OSError) as error:
        typer.echo(json.dumps({"error": str(error)}), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(contract.model_dump_json())
    typer.echo(
        shlex.join(
            ["shipyard", "run", str(contract.run_id), "--context", str(context)]
        ),
        err=True,
    )


@app.command()
def inspect(
    run_id: UUID,
    runs_dir: Annotated[
        Path, typer.Option(help="Filesystem Runs root.")
    ] = _DEFAULT_RUNS,
) -> None:
    """Validate and print a saved contract without reading its original inputs."""
    try:
        contract = FileRunStore(root=runs_dir).load(run_id)
    except ValueError as error:
        _fail(error)
    typer.echo(contract.model_dump_json())


@app.command()
def methodology(
    run_id: UUID,
    runs_dir: Annotated[
        Path, typer.Option(help="Filesystem Runs root.")
    ] = _DEFAULT_RUNS,
    stage: Annotated[
        ArtifactStage | None,
        typer.Option(help="Preview guidance for one native-agent stage."),
    ] = None,
) -> None:
    """Preview saved methodology; does not execute or modify the Run."""
    try:
        contract = FileRunStore(root=runs_dir).load(run_id)
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


@app.command("run")
def run_command(
    run_id: UUID,
    repo: Annotated[
        Path | None, typer.Option(help="Target repository containing the frozen base.")
    ] = None,
    runs_dir: Annotated[Path | None, typer.Option(help="Filesystem Runs root.")] = None,
    context: Annotated[
        Path | None, typer.Option(help="Saved per-Run execution context file.")
    ] = None,
    workspace: Annotated[
        Path | None, typer.Option(help="Fresh isolated workspace path.")
    ] = None,
) -> None:
    """Execute a captured CREATED Run synchronously and write terminal evidence."""
    from shipyard.agents.codex import CodexAgent
    from shipyard.application.execution import execute_run
    from shipyard.domain import RunLifecycle, RunOutcome

    try:
        if context is not None:
            locator = load_context(path=context, run_id=run_id)
            if (
                repo is not None
                and GitRepository(path=repo).checkout_root() != locator.repository
            ):
                raise ValueError(
                    f"Conflicting --repo {repo}; expected {locator.repository}. "
                    "Use the matching repository or omit --repo with --context"
                )
            if runs_dir is not None and runs_dir.resolve() != locator.runs_root:
                raise ValueError(
                    f"Conflicting --runs-dir {runs_dir}; expected {locator.runs_root}. "
                    "Use the matching Runs root or omit --runs-dir with --context"
                )
            repo = locator.repository
            runs_dir = locator.runs_root
        else:
            repo = repo if repo is not None else Path(".")
            runs_dir = (runs_dir if runs_dir is not None else _DEFAULT_RUNS).resolve()
        evidence = execute_run(
            store=FileRunStore(root=runs_dir),
            run_id=run_id,
            repository=GitRepository(path=repo),
            workspace=workspace,
            agent=CodexAgent(),
        )
    except (ValueError, OSError) as error:
        typer.echo(json.dumps({"error": str(error)}), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {
                "run": evidence.run.model_dump(mode="json"),
                "report": str((runs_dir / str(run_id) / "report.md").resolve()),
                "evidence": str((runs_dir / str(run_id) / "evidence.json").resolve()),
            }
        )
    )
    if evidence.run.lifecycle == RunLifecycle.CANCELLED:
        raise typer.Exit(code=130)
    if evidence.run.lifecycle == RunLifecycle.FAILED:
        raise typer.Exit(code=1)
    if evidence.run.outcome != RunOutcome.VERIFIED:
        raise typer.Exit(code=2)
