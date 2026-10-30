"""Versioned application receipts, separate from revision-bound verification."""

from datetime import datetime
from pathlib import Path
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from shipyard.domain.candidate import GitCommitSha


class ApplicationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[1] = 1
    run_id: UUID
    candidate_sha: GitCommitSha
    repository: Path
    branch: str
    previous_sha: GitCommitSha
    resulting_sha: GitCommitSha
    timestamp: datetime
    operation: Literal["advanced", "observed_noop"]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            not self.repository.is_absolute()
            or self.repository.resolve() != self.repository
            or not self.branch
            or self.timestamp.utcoffset() is None
            or self.resulting_sha != self.candidate_sha
            or (
                self.operation == "observed_noop"
                and self.previous_sha != self.resulting_sha
            )
        ):
            raise ValueError("Invalid application receipt identity/result/timestamp")
        return self
