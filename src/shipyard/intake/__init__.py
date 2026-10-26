"""Source adapters for capturing intent without advancing a Run."""

from shipyard.intake.markdown import MarkdownIntakeError, read_markdown_intent

__all__ = ["MarkdownIntakeError", "read_markdown_intent"]
