"""Identity and starting revision of one execution within a Run."""

from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from harborist.domain.candidate import Candidate
from harborist.domain.revision import GitCommitSha


class Attempt(BaseModel):
    """An immutable execution identity without lifecycle or orchestration rules."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attempt_id: UUID
    run_id: UUID
    start_sha: GitCommitSha

    @classmethod
    def create(cls, run_id: UUID, start_sha: GitCommitSha) -> Self:
        """Create a fresh Attempt belonging to the supplied Run."""
        return cls(attempt_id=uuid4(), run_id=run_id, start_sha=start_sha)

    def create_candidate(self, candidate_sha: GitCommitSha) -> Candidate:
        """Describe a candidate for this Attempt without changing the Attempt."""
        return Candidate(attempt_id=self.attempt_id, candidate_sha=candidate_sha)
