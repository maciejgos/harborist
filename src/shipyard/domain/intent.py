"""Captured source text and its storage-independent artifact identity."""

import hashlib
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

from shipyard.domain.artifact import ArtifactKind, ArtifactReference, ArtifactStage


def _validate_utf8(value: str) -> str:
    value.encode("utf-8")
    return value


type _MarkdownText = Annotated[
    str, StringConstraints(strict=True), AfterValidator(_validate_utf8)
]

_MARKDOWN_ADAPTER = TypeAdapter(_MarkdownText)


class IntentSnapshot(BaseModel):
    """An in-memory source capture, independent of subsequent source changes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: Annotated[str, StringConstraints(strict=True, min_length=1)]
    markdown: _MarkdownText
    artifact: ArtifactReference

    @model_validator(mode="after")
    def validate_artifact(self) -> Self:
        if (
            self.artifact.kind != ArtifactKind.INTENT
            or self.artifact.produced_by != ArtifactStage.INTAKE
            or self.artifact.attempt_id is not None
        ):
            raise ValueError(
                "Intent artifact must be Run-owned INTENT produced by INTAKE"
            )
        content = self.markdown.encode("utf-8")
        if (
            self.artifact.size_bytes != len(content)
            or self.artifact.sha256 != hashlib.sha256(content).hexdigest()
        ):
            raise ValueError(
                "Intent artifact digest and size must match Markdown content"
            )
        return self

    @property
    def run_id(self) -> UUID:
        return self.artifact.run_id

    @classmethod
    def create(cls, *, run_id: UUID, source_ref: str, markdown: str) -> Self:
        markdown = _MARKDOWN_ADAPTER.validate_python(markdown)
        return cls(
            source_ref=source_ref,
            markdown=markdown,
            artifact=ArtifactReference.create(
                run_id=run_id,
                kind=ArtifactKind.INTENT,
                produced_by=ArtifactStage.INTAKE,
                content=markdown.encode("utf-8"),
            ),
        )
