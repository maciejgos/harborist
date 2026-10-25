"""Storage-independent artifact identity and declared provenance."""

import hashlib
from enum import StrEnum
from typing import Annotated, Self, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ArtifactKind(StrEnum):
    INTENT = "intent"
    SPEC = "spec"
    PLAN = "plan"
    REVIEW = "review"
    REPORT = "report"
    STAGE_RESULT = "stage_result"
    TEST_EVIDENCE = "test_evidence"
    EVIDENCE = "evidence"
    LOG = "log"


class ArtifactStage(StrEnum):
    INTAKE = "intake"
    DESIGN = "design"
    PLAN = "plan"
    BUILD = "build"
    TEST = "test"
    REVIEW = "review"
    PACKAGE = "package"


type ArtifactSha256 = Annotated[
    str, StringConstraints(strict=True, pattern=r"\A[0-9a-f]{64}\z")
]


class ArtifactReference(BaseModel):
    """An immutable artifact version, without content or storage location.

    Direct construction validates metadata only. Declared ownership and origin do
    not establish execution, authenticity, durability, or verification.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: UUID
    run_id: UUID
    kind: ArtifactKind
    produced_by: ArtifactStage
    sha256: ArtifactSha256
    size_bytes: Annotated[int, Field(strict=True, ge=0)]
    attempt_id: UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        run_id: UUID,
        kind: ArtifactKind,
        produced_by: ArtifactStage,
        content: bytes,
        attempt_id: UUID | None = None,
    ) -> Self:
        """Describe exact supplied bytes without encoding, normalization, or I/O."""
        if not isinstance(cast(object, content), bytes):
            raise TypeError("Artifact content must be bytes")
        return cls(
            artifact_id=uuid4(),
            run_id=run_id,
            kind=kind,
            produced_by=produced_by,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            attempt_id=attempt_id,
        )
