"""Syntax-only Git commit identity; repository checks belong to the Git adapter."""

from typing import Annotated

from pydantic import StringConstraints

type GitCommitSha = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"\A(?:[0-9a-f]{40}|[0-9a-f]{64})\z"),
]
