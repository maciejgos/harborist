"""Local Markdown file intake; semantic normalization and storage are deferred."""

from pathlib import Path
from uuid import UUID

from shipyard.domain import IntentSnapshot


class MarkdownIntakeError(ValueError):
    """A source file could not be read as UTF-8 Markdown."""


def read_markdown_intent(*, run_id: UUID, path: Path) -> IntentSnapshot:
    """Capture exact UTF-8 source content without modifying the filesystem."""
    try:
        resolved = path.resolve(strict=True)
        markdown = resolved.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise MarkdownIntakeError(
            f"Cannot read Markdown source {path}: {error}"
        ) from error
    return IntentSnapshot.create(
        run_id=run_id, source_ref=f"file:{resolved}", markdown=markdown
    )
