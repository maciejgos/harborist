"""An exact candidate revision owned by an Attempt."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shipyard.domain.revision import GitCommitSha


class Candidate(BaseModel):
    """A separate immutable record, identified by Attempt ID and commit SHA.

    This record does not assert repository existence or verification status.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_id: UUID
    candidate_sha: GitCommitSha
