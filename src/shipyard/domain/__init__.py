"""Infrastructure-independent Run, Attempt, and candidate contracts."""

from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.revision import GitCommitSha
from shipyard.domain.run import (
    FailureReason,
    InvalidRunTransition,
    Run,
    RunLifecycle,
    RunOutcome,
)

__all__ = [
    "Attempt",
    "Candidate",
    "FailureReason",
    "GitCommitSha",
    "InvalidRunTransition",
    "Run",
    "RunLifecycle",
    "RunOutcome",
]
