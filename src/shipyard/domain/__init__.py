"""Infrastructure-independent workflow and evidence contracts."""

from shipyard.domain.artifact import (
    ArtifactKind,
    ArtifactReference,
    ArtifactSha256,
    ArtifactStage,
)
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.event import (
    AttemptCreatedEvent,
    DomainEvent,
    RunEvent,
    RunEventType,
)
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
    "AttemptCreatedEvent",
    "BuildStageResult",
    "Candidate",
    "CriterionResult",
    "CriterionStatus",
    "DesignStageResult",
    "DomainEvent",
    "FailureReason",
    "GitCommitSha",
    "InvalidRunTransition",
    "InvalidStageOutput",
    "PlanStageResult",
    "ReviewStageResult",
    "ReviewSummary",
    "Run",
    "RunEvent",
    "RunEventType",
    "RunLifecycle",
    "RunOutcome",
    "StageResult",
    "StageStatus",
    "parse_stage_result",
]
