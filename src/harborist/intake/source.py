"""Dispatch supported sources into the common immutable intent representation."""

from pathlib import Path
from uuid import UUID

from harborist.domain import IntentSnapshot
from harborist.intake.github import read_github_intent
from harborist.intake.markdown import read_markdown_intent


class IntakeSourceError(ValueError):
    """An intake selector is unsupported or empty."""


def capture_intent(*, run_id: UUID, source: str) -> IntentSnapshot:
    if source.startswith("file:") and source[5:]:
        return read_markdown_intent(run_id=run_id, path=Path(source[5:]))
    if source.startswith("github:"):
        return read_github_intent(run_id=run_id, source=source)
    raise IntakeSourceError("Expected file:path or github:owner/repo#number")
