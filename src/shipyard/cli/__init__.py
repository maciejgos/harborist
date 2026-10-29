"""CLI presentation for frozen capture, synchronous execution and inspection."""

import json
import os
import shlex
from pathlib import Path
from typing import Annotated, NoReturn
from uuid import UUID

import typer

from shipyard.application import create_run
from shipyard.application.context import ExecutionContext, load_context
from shipyard.configuration import SettingsError, load_execution_settings
from shipyard.domain import ArtifactStage, ExecutionBudget, RunContract
from shipyard.git import GitRepository
from shipyard.git.repository import GitWorkspaceError
from shipyard.intake.github import parse_github_selector
from shipyard.paths import runs_root
from shipyard.persistence import FileRunStore
from shipyard.skills import compile_methodology, compose_guidance

app = typer.Typer(
    no_args_is_help=True, help="Freeze, execute and inspect Shipyard Runs."
)


def _fail(error: ValueError) -> NoReturn:
    typer.echo(json.dumps({"error": str(error)}), err=True)
    raise typer.Exit(code=1)


def _capture_run(
    *,
    source: str,
    settings: Path | None,
    repo: Path,
    ref: str,
    runs_dir: Path | None,
    timeout: int,
    verification_reserve: int,
) -> tuple[RunContract, Path, Path]:
    """Share intake preparation and its single durable capture, without output."""
    repository = GitRepository(path=repo)
    root = repository.checkout_root()
    selected_settings = (
        settings if settings is not None else root / "shipyard.settings.yaml"
    )
    budget = ExecutionBudget(
        total_seconds=timeout, verification_reserve_seconds=verification_reserve
    )
    try:
        execution = load_execution_settings(path=selected_settings, budget=budget)
        compile_methodology(execution)
    except ValueError as error:
        raise SettingsError(
            f"Invalid execution settings {selected_settings}: {error}. "
            "Supply --settings PATH to select a valid file; relative explicit "
            "paths use the invocation directory."
        ) from error
    runs_dir = (runs_dir if runs_dir is not None else runs_root()).resolve()
    contract = create_run(
        source=source,
        repository=GitRepository(path=root),
        store=FileRunStore(root=runs_dir),
        execution=execution,
        ref=ref,
    )
    ExecutionContext(
        version=1, run_id=contract.run_id, repository=root, runs_root=runs_dir
    ).save()
    return contract, root, runs_dir


def _execution_command(
    run_id: UUID, runs_dir: Path, workspace: Path | None = None
) -> str:
    arguments = ["shipyard", "run", str(run_id)]
    if runs_dir != runs_root().resolve():
        arguments += ["--runs-dir", str(runs_dir)]
    if workspace is not None:
        arguments += ["--workspace", str(workspace)]
    return shlex.join(arguments)


@app.command()
def intake(
    source: Annotated[
        str, typer.Argument(help="file:path or github:owner/repo#number")
    ],
    settings: Annotated[
        Path | None,
        typer.Option(
            help="Optional operator YAML override; methodology paths resolve beside it."
        ),
    ] = None,
    repo: Annotated[
        Path, typer.Option(help="Target implementation repository.")
    ] = Path("."),
    ref: Annotated[str, typer.Option(help="Base commit-ish, resolved once.")] = "HEAD",
    runs_dir: Annotated[
        Path | None,
        typer.Option(help="Filesystem Runs root (default: ~/.shipyard/runs)."),
    ] = None,
    timeout: Annotated[
        int, typer.Option(help="Overall execution budget in seconds.", min=1)
    ] = 1800,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print the full frozen contract as JSON.")
    ] = False,
    verification_reserve: Annotated[
        int, typer.Option(help="Seconds reserved for verification.", min=1)
    ] = 300,
) -> None:
    """Capture a CREATED Run and print a human-readable summary.

    Defaults to shipyard.settings.yaml at the target checkout root selected by
    --repo (default: .), including from subdirectories. --settings PATH takes
    precedence; relative explicit paths use the invocation directory.
    Methodology paths resolve beside the selected settings file. On missing or
    invalid settings, supply --settings PATH. No other locations are searched.

    Existing scripts consuming JSON stdout must add --json for the full frozen contract.
    Prints shipyard run <run-id>; custom storage adds only --runs-dir.
    Does not execute agents or verification checks.
    """
    try:
        contract, root, runs_dir = _capture_run(
            source=source,
            settings=settings,
            repo=repo,
            ref=ref,
            runs_dir=runs_dir,
            timeout=timeout,
            verification_reserve=verification_reserve,
        )
    except (ValueError, OSError) as error:
        typer.echo(json.dumps({"error": str(error)}), err=True)
        raise typer.Exit(code=1) from error
    command = _execution_command(contract.run_id, runs_dir)
    if json_output:
        typer.echo(contract.model_dump_json())
        typer.echo(command, err=True)
    else:
        typer.echo(
            f"Run captured\n"
            f"ID:         {contract.run_id}\n"
            f"Repository: {root}\n"
            f"Base:       {contract.base_sha}\n"
            f"Task:       {contract.intent.source_ref}\n"
            f"Status:     CREATED\n\n"
            f"Execute:\n  {command}"
        )


@app.command()
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
    typer.echo(contract.model_dump_json())


@app.command()
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


@app.command("run")
def run_command(
    run_id: Annotated[
        str, typer.Argument(help="Run UUID, file:path or github:owner/repo#number.")
    ],
    settings: Annotated[
        Path | None, typer.Option(help="Source capture only: operator YAML override.")
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option(help="Source capture only: base commit-ish (default HEAD)."),
    ] = None,
    timeout: Annotated[
        int | None,
        typer.Option(help="Source capture only: total seconds (default 1800).", min=1),
    ] = None,
    verification_reserve: Annotated[
        int | None,
        typer.Option(
            help="Source capture only: reserved seconds (default 300).", min=1
        ),
    ] = None,
    repo: Annotated[
        Path | None,
        typer.Option(
            help="Repository constraint; must match saved context when present."
        ),
    ] = None,
    runs_dir: Annotated[
        Path | None,
        typer.Option(
            help="Runs root for automatic context lookup (default: ~/.shipyard/runs); must match context."
        ),
    ] = None,
    context: Annotated[
        Path | None,
        typer.Option(
            help="Explicit context locator; takes precedence over automatic lookup."
        ),
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print the full Run result as JSON.")
    ] = False,
    workspace: Annotated[
        Path | None, typer.Option(help="Fresh isolated workspace path.")
    ] = None,
) -> None:
    """Capture a source then execute, or execute a saved Run UUID synchronously.

    Sources accept file:<nonempty-path> and github:owner/repo#positive-issue-number.
    Source capture uses shipyard.settings.yaml at the target checkout root,
    including subdirectories. --settings PATH takes precedence; relative explicit
    paths use the invocation directory. Invalid settings never fall back.
    --settings, --ref, --timeout and --verification-reserve apply only to source
    capture; UUIDs use frozen inputs. --context selects an existing Run only.
    Both modes support --repo, --runs-dir, --workspace and --json.
    If capture succeeds but preflight fails, the CREATED Run is retained and a
    UUID recovery command is printed. Use a fresh external --workspace to correct
    placement. Execution never recaptures or automatically retries.

    Automatically loads <runs-root>/<run-id>/execution-context.json, independently
    of cwd. Custom storage requires --runs-dir; no global discovery is performed.
    Explicit --context takes precedence; --repo and --runs-dir must match it.
    Only absent automatic context permits legacy --repo/cwd and storage defaults;
    invalid existing context fails closed without repair. From a development
    checkout use uv run shipyard run <run-id>.

    Human output ends with a terminal summary and report/evidence locations.
    Scripts consuming the previous JSON default must add --json.
    Writes terminal evidence; verification does not apply the candidate.
    """
    from shipyard.agents.codex import CodexAgent
    from shipyard.application.execution import execute_run
    from shipyard.cli.progress import ProgressReporter
    from shipyard.cli.run_summary import artifact_paths, render_summary, single_line
    from shipyard.domain import RunLifecycle, RunOutcome

    captured = False
    try:
        source_mode = run_id.startswith(("file:", "github:"))
        if source_mode:
            if run_id.startswith("file:") and not run_id[5:]:
                raise ValueError(
                    "Expected file:<nonempty-path>; supply a readable Markdown file."
                )
            if run_id.startswith("github:"):
                parse_github_selector(run_id)
            if context is not None:
                raise ValueError(
                    "--context selects an existing Run; omit it to capture a source."
                )
            contract, repo, runs_dir = _capture_run(
                source=run_id,
                settings=settings,
                repo=repo if repo is not None else Path("."),
                ref=ref if ref is not None else "HEAD",
                runs_dir=runs_dir,
                timeout=timeout if timeout is not None else 1800,
                verification_reserve=verification_reserve
                if verification_reserve is not None
                else 300,
            )
            execution_id = contract.run_id
            captured = True
            typer.echo(f"Captured Run: {execution_id} (CREATED)", err=True)
        else:
            try:
                execution_id = UUID(run_id)
            except ValueError as error:
                raise ValueError(
                    "Expected an existing Run UUID, file:<nonempty-path> or github:owner/repo#positive-issue-number."
                ) from error
            supplied = [
                name
                for name, value in (
                    ("--settings", settings),
                    ("--ref", ref),
                    ("--timeout", timeout),
                    ("--verification-reserve", verification_reserve),
                )
                if value is not None
            ]
            if supplied:
                raise ValueError(
                    f"{', '.join(supplied)} apply only to source capture. Execute the saved Run UUID without these options, "
                    "or use shipyard run file:PATH / github:owner/repo#number to create a new capture."
                )
    except (ValueError, OSError) as error:
        typer.echo(json.dumps({"error": str(error)}), err=True)
        raise typer.Exit(code=1) from error

    with ProgressReporter() as reporter:
        reporter.line(f"Run: {execution_id}")
        phase = "Execution context resolution"
        try:
            selected_context = context
            if selected_context is None:
                selected_root = (
                    runs_dir if runs_dir is not None else runs_root()
                ).resolve()
                automatic = selected_root / str(execution_id) / "execution-context.json"
                try:
                    automatic.lstat()
                except FileNotFoundError:
                    pass  # Only an absent automatic locator permits historical fallback.
                except OSError as error:
                    raise ValueError(
                        f"Invalid execution context {automatic}: {error}"
                    ) from error
                else:
                    selected_context = automatic
            if selected_context is not None:
                locator = load_context(path=selected_context, run_id=execution_id)
                if repo is not None:
                    try:
                        matching_repo = (
                            GitRepository(path=repo).checkout_root()
                            == locator.repository
                        )
                    except ValueError as error:
                        raise ValueError(
                            f"Conflicting --repo {repo}; expected {locator.repository}: {error}"
                        ) from error
                    if not matching_repo:
                        raise ValueError(
                            f"Conflicting --repo {repo}; expected {locator.repository}"
                        )
                if runs_dir is not None and runs_dir.resolve() != locator.runs_root:
                    raise ValueError(
                        f"Conflicting --runs-dir {runs_dir}; expected {locator.runs_root}"
                    )
                repo = locator.repository
                runs_dir = locator.runs_root
            else:
                repo = repo if repo is not None else Path(".")
                runs_dir = (runs_dir if runs_dir is not None else runs_root()).resolve()
            phase = "Execution preflight"
            evidence = execute_run(
                store=FileRunStore(root=runs_dir),
                run_id=execution_id,
                repository=GitRepository(path=repo),
                workspace=workspace,
                agent=CodexAgent(),
                progress=reporter.update,
            )
        except KeyboardInterrupt as error:
            interrupted_phase = phase
            if reporter.last is not None:
                interrupted_phase = (
                    "Finalization"
                    if reporter.last.stage.value == "package"
                    and reporter.last.state == "skipped"
                    else reporter.last.stage.value.upper()
                )
            reporter.line(
                single_line(
                    f"{interrupted_phase} cancelled by operator; terminal artifacts unavailable"
                )
            )
            if reporter.last is None:
                reporter.line(
                    "DESIGN, PLAN, BUILD, TEST, REVIEW, PACKAGE skipped (cancelled before execution)"
                )
            package_interrupted = (
                reporter.last is not None and reporter.last.stage.value == "package"
            )
            raise typer.Exit(code=1 if package_interrupted else 130) from error
        except Exception as error:
            if reporter.last is not None and reporter.last.stage.value == "package":
                phase = (
                    "PACKAGE" if reporter.last.state != "skipped" else "Finalization"
                )
            elif reporter.last is not None:
                phase = reporter.last.stage.value.upper()
            retained_created = False
            if captured and runs_dir is not None:
                try:
                    retained_created = (
                        FileRunStore(root=runs_dir).load_state(execution_id).lifecycle
                        == RunLifecycle.CREATED
                    )
                except ValueError, OSError:
                    pass
            if (retained_created and isinstance(error, ValueError)) or (
                reporter.last is None
                and (
                    isinstance(error, GitWorkspaceError)
                    or (
                        phase == "Execution context resolution"
                        and isinstance(error, ValueError)
                    )
                )
            ):
                detail = str(error)
            elif isinstance(error, OSError) and error.errno is not None:
                detail = f"{type(error).__name__}: {os.strerror(error.errno)}; check Runs storage access and capacity"
            else:
                detail = f"{type(error).__name__}; inspect retained Run records and execution settings"
            reporter.line(
                single_line(
                    f"{phase} failed; terminal artifacts unavailable: {detail}"
                )[:1024]
            )
            if reporter.last is None:
                reporter.line(
                    "DESIGN, PLAN, BUILD, TEST, REVIEW, PACKAGE skipped (execution could not begin)"
                )
            if retained_created and runs_dir is not None:
                # Offer recovery only for a durable capture that was never admitted.
                reporter.line(
                    f"Run {execution_id} retained in CREATED; correct the preflight problem without recapturing."
                )
                recovery_workspace = None
                if isinstance(error, GitWorkspaceError):
                    reporter.line(
                        "Select a fresh external --workspace outside the source checkout and Runs records."
                    )
                    recovery_workspace = (
                        Path.home()
                        / ".shipyard"
                        / "workspaces"
                        / f"{execution_id}-corrected"
                    )
                reporter.line("Recover with:")
                reporter.line(
                    _execution_command(execution_id, runs_dir, recovery_workspace)
                )
            raise typer.Exit(code=1) from error
        reporter.line(
            f"Result: {evidence.run.outcome or evidence.run.failure_reason or evidence.run.lifecycle}"
        )
        reporter.line(single_line(f"Workspace: {evidence.workspace or 'unknown'}"))
        directory = runs_dir / str(execution_id)
        for label, path in artifact_paths(directory).items():
            reporter.line(single_line(f"{label}: {path}"))
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "run": evidence.run.model_dump(mode="json"),
                    "workspace": str(evidence.workspace)
                    if evidence.workspace
                    else None,
                    "report": str(
                        (runs_dir / str(execution_id) / "report.md").resolve()
                    ),
                    "evidence": str(
                        (runs_dir / str(execution_id) / "evidence.json").resolve()
                    ),
                }
            )
        )
    else:
        typer.echo(render_summary(evidence, directory))
    if evidence.run.lifecycle == RunLifecycle.CANCELLED:
        raise typer.Exit(code=130)
    if evidence.run.lifecycle == RunLifecycle.FAILED:
        raise typer.Exit(code=1)
    if evidence.run.outcome != RunOutcome.VERIFIED:
        raise typer.Exit(code=2)
