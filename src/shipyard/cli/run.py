"""Background submission with explicit synchronous compatibility mode."""

import json
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer

from shipyard.application.context import resolve_context
from shipyard.cli.capture import capture_run, execution_command
from shipyard.git import GitRepository
from shipyard.git.repository import GitWorkspaceError
from shipyard.intake.github import parse_github_selector
from shipyard.paths import runs_root
from shipyard.persistence import FileRunStore


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
    foreground: Annotated[
        bool,
        typer.Option(
            "--foreground",
            help="Execute synchronously in this terminal instead of submitting.",
        ),
    ] = False,
    control_dir: Annotated[
        Path | None,
        typer.Option(
            help="Background service directory (default ~/.shipyard/control)."
        ),
    ] = None,
    workspace: Annotated[
        Path | None, typer.Option(help="Fresh isolated workspace path.")
    ] = None,
) -> None:
    """Capture a source or submit a saved Run to the local background service.

    Start the service with shipyard service start. Submission returns promptly;
    closing this terminal does not stop execution. Use --foreground for the
    original synchronous behavior and terminal-result exit codes. Background
    exit zero means durable acceptance, not VERIFIED. --json returns the delivery
    record in background mode. Use shipyard status RUN_ID to monitor.

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

    Foreground human output ends with a terminal summary and report/evidence locations.
    Scripts consuming the previous synchronous JSON must add --foreground --json.
    Writes terminal evidence; verification does not apply the candidate.
    """
    from shipyard.agents.codex import CodexAgent
    from shipyard.application.execution import execute_run
    from shipyard.cli.progress import ProgressReporter
    from shipyard.cli.run_summary import (
        application_guidance,
        artifact_paths,
        render_summary,
        single_line,
    )
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
            contract, repo, runs_dir = capture_run(
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

    if not foreground:
        from shipyard.cli.service import control_root
        from shipyard.control.client import ControlClient
        from shipyard.control.queue import Submission

        try:
            selected_repo, selected_root = resolve_context(
                run_id=execution_id,
                repo=repo,
                runs_dir=runs_dir,
                context=context,
                default_root=runs_root(),
            )
            submission = Submission(
                run_id=execution_id,
                repository=selected_repo,
                runs_root=selected_root,
                workspace=workspace.resolve() if workspace is not None else None,
            )
            record = ControlClient(control_root(control_dir)).request(
                "POST", "/runs", submission.model_dump(mode="json")
            )
        except (ValueError, OSError) as error:
            typer.echo(str(error), err=True)
            typer.echo(
                f"Run {execution_id} retained; inspect or submit this UUID after correcting the problem.",
                err=True,
            )
            raise typer.Exit(1) from error
        if json_output:
            typer.echo(json.dumps(record))
        else:
            typer.echo(
                f"Run: {execution_id}\nDelivery: {record['state']}\nUse shipyard status {execution_id} to monitor."
            )
        return

    with ProgressReporter() as reporter:
        reporter.line(f"Run: {execution_id}")
        phase = "Execution context resolution"
        try:
            repo, runs_dir = resolve_context(
                run_id=execution_id,
                repo=repo,
                runs_dir=runs_dir,
                context=context,
                default_root=runs_root(),
            )
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
                    execution_command(execution_id, runs_dir, recovery_workspace)
                    + " --foreground"
                )
            raise typer.Exit(code=1) from error
        reporter.line(
            f"Result: {evidence.run.outcome or evidence.run.failure_reason or evidence.run.lifecycle}"
        )
        reporter.line(single_line(f"Workspace: {evidence.workspace or 'unknown'}"))
        directory = FileRunStore(root=runs_dir).directory(execution_id)
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
                    "report": str((directory / "report.md").resolve()),
                    "evidence": str((directory / "evidence.json").resolve()),
                }
            )
        )
    else:
        typer.echo(render_summary(evidence, directory))
    if evidence.run.outcome == RunOutcome.VERIFIED:
        for line in application_guidance(
            run_id=execution_id, repository=repo, root=runs_dir
        ):
            typer.echo(line, err=json_output)
    if evidence.run.lifecycle == RunLifecycle.CANCELLED:
        raise typer.Exit(code=130)
    if evidence.run.lifecycle == RunLifecycle.FAILED:
        raise typer.Exit(code=1)
    if evidence.run.outcome != RunOutcome.VERIFIED:
        raise typer.Exit(code=2)
