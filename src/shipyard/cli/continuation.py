"""Explicit local continuation commands."""

import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import typer

from shipyard.agents.codex import CodexAgent
from shipyard.application.context import resolve_context
from shipyard.application.execution import execute_run
from shipyard.cli.progress import ProgressReporter
from shipyard.cli.run_summary import render_summary
from shipyard.cli.service import control_root
from shipyard.control.client import ControlClient
from shipyard.control.queue import Submission
from shipyard.domain import RunLifecycle, RunOutcome
from shipyard.domain.attempt import Attempt
from shipyard.domain.continuation import ContinuationRequest, GitHubFeedbackSelection
from shipyard.git import GitRepository
from shipyard.persistence import FileRunStore
from shipyard.persistence.continuation import prepare_continuation


def _continue(
    action: Literal["rework", "recover"],
    run_id: UUID,
    feedback: str,
    additional_seconds: int,
    repo: Path | None,
    runs_dir: Path | None,
    context: Path | None,
    workspace: Path | None,
    foreground: bool,
    control_dir: Path | None,
    json_output: bool,
    expected_attempt: UUID | None,
    observation: Path | None = None,
    feedback_ids: list[str] | None = None,
) -> None:
    try:
        repository, root = resolve_context(
            run_id=run_id, repo=repo, runs_dir=runs_dir, context=context
        )
        store = FileRunStore(root=root)
        store.load(run_id)
        previous = Attempt.model_validate_json(
            (store.directory(run_id) / "attempt.json").read_bytes()
        )
        selection = None
        if observation is not None or feedback_ids:
            if observation is None or not feedback_ids:
                raise ValueError("Supply both --observation and --feedback-id")
            selection = GitHubFeedbackSelection(
                observation=observation.resolve(), ids=tuple(feedback_ids)
            )
        request = ContinuationRequest(
            action=action,
            expected_attempt_id=expected_attempt or previous.attempt_id,
            feedback=feedback,
            github_feedback=selection,
            additional_seconds=additional_seconds,
        )
        if not foreground:
            submission = Submission(
                run_id=run_id,
                repository=repository,
                runs_root=root,
                workspace=workspace.resolve() if workspace is not None else None,
                continuation=request,
            )
            record = ControlClient(control_root(control_dir)).request(
                "POST", "/runs", submission.model_dump(mode="json")
            )
            typer.echo(
                json.dumps(record)
                if json_output
                else f"Run: {run_id}\nAction: {action}\nDelivery: {record['state']}\nUse shipyard status {run_id} to monitor."
            )
            return
        # Preflight Git/workspace before reserving a new immutable Attempt.
        git = GitRepository(path=repository)
        _, preview = prepare_continuation(
            store=store, run_id=run_id, request=request, dry_run=True
        )
        if workspace is not None:
            from shipyard.application.workspace import validate_workspace_placement

            validate_workspace_placement(
                path=workspace, run_directory=store.original_directory(run_id)
            )
            git.preflight_workspace(base_sha=preview.attempt.start_sha, path=workspace)
        selected, record = prepare_continuation(
            store=store, run_id=run_id, request=request
        )
        with ProgressReporter() as reporter:
            reporter.line(f"Run: {run_id}; Attempt: {record.attempt.attempt_id}")
            evidence = execute_run(
                store=selected,
                run_id=run_id,
                repository=git,
                workspace=workspace,
                agent=CodexAgent(),
                progress=reporter.update,
            )
        directory = selected.directory(run_id)
        typer.echo(
            json.dumps(
                {
                    "run": evidence.run.model_dump(mode="json"),
                    "attempt": evidence.attempt.model_dump(mode="json")
                    if evidence.attempt
                    else None,
                    "report": str(directory / "report.md"),
                    "evidence": str(directory / "evidence.json"),
                }
            )
            if json_output
            else render_summary(evidence, directory)
        )
    except (ValueError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    if evidence.run.lifecycle == RunLifecycle.CANCELLED:
        raise typer.Exit(130)
    if evidence.run.lifecycle == RunLifecycle.FAILED:
        raise typer.Exit(1)
    if evidence.run.outcome != RunOutcome.VERIFIED:
        raise typer.Exit(2)


def rework(
    run_id: UUID,
    feedback: Annotated[
        str, typer.Option(help="Feedback to PLAN; the spec stays frozen.")
    ] = "",
    additional_seconds: Annotated[
        int, typer.Option(min=0, help="Explicit additional Run time.")
    ] = 0,
    repo: Annotated[Path | None, typer.Option()] = None,
    runs_dir: Annotated[Path | None, typer.Option()] = None,
    context: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path | None, typer.Option()] = None,
    foreground: Annotated[bool, typer.Option("--foreground")] = False,
    control_dir: Annotated[Path | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    expected_attempt: Annotated[
        UUID | None, typer.Option(help="Reject if the latest Attempt changed.")
    ] = None,
    observation: Annotated[
        Path | None, typer.Option(help="Saved GitHub PR observation.")
    ] = None,
    feedback_id: Annotated[
        list[str] | None,
        typer.Option(help="Explicit review or comment ID, repeatable."),
    ] = None,
) -> None:
    """Create a fresh PLAN → BUILD → TEST → REVIEW Attempt after rejected software."""
    _continue(
        "rework",
        run_id,
        feedback,
        additional_seconds,
        repo,
        runs_dir,
        context,
        workspace,
        foreground,
        control_dir,
        json_output,
        expected_attempt,
        observation,
        feedback_id,
    )


def recover(
    run_id: UUID,
    additional_seconds: Annotated[
        int,
        typer.Option(
            min=0,
            help="Explicit additional Run time; required for interrupted captures.",
        ),
    ] = 0,
    repo: Annotated[Path | None, typer.Option()] = None,
    runs_dir: Annotated[Path | None, typer.Option()] = None,
    context: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path | None, typer.Option()] = None,
    foreground: Annotated[bool, typer.Option("--foreground")] = False,
    control_dir: Annotated[Path | None, typer.Option()] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    expected_attempt: Annotated[
        UUID | None, typer.Option(help="Reject if the latest Attempt changed.")
    ] = None,
) -> None:
    """Recover an eligible execution failure with fresh invocations and remaining time."""
    _continue(
        "recover",
        run_id,
        "",
        additional_seconds,
        repo,
        runs_dir,
        context,
        workspace,
        foreground,
        control_dir,
        json_output,
        expected_attempt,
    )
