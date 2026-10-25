"""Infrastructure-independent workflow and evidence contracts."""

from shipyard.domain.artifact import (
    ArtifactKind,
    ArtifactReference,
    ArtifactSha256,
    ArtifactStage,
)
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
from shipyard.domain.stage_result import (
    AgentStage,
    BuildStageResult,
    CriterionResult,
    CriterionStatus,
    DesignStageResult,
    InvalidStageOutput,
    PlanStageResult,
    ReviewStageResult,
    ReviewSummary,
    StageResult,
    StageStatus,
    parse_stage_result,
)

__all__ = [
    "AgentStage",
    "ArtifactKind",
    "ArtifactReference",
    "ArtifactSha256",
    "ArtifactStage",
    "Attempt",
    "BuildStageResult",
    "Candidate",
    "CriterionResult",
    "CriterionStatus",
    "DesignStageResult",
    "FailureReason",
    "GitCommitSha",
    "InvalidRunTransition",
    "InvalidStageOutput",
    "PlanStageResult",
    "ReviewStageResult",
    "ReviewSummary",
    "Run",
    "RunLifecycle",
    "RunOutcome",
    "StageResult",
    "StageStatus",
    "parse_stage_result",
]
