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
from shipyard.domain.execution import (
    AgentProfile,
    ExecutionBudget,
    ExecutionSnapshot,
    MethodologyAsset,
)
from shipyard.domain.intent import IntentSnapshot
from shipyard.domain.revision import GitCommitSha
from shipyard.domain.run import (
    FailureReason,
    InvalidRunTransition,
    Run,
    RunLifecycle,
    RunOutcome,
)
from shipyard.domain.run_contract import RunContract
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
from shipyard.domain.verification import (
    VerificationCheck,
    VerificationConfig,
    VerificationConfigSnapshot,
)

__all__ = [
    "AgentProfile",
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
    "ExecutionBudget",
    "ExecutionSnapshot",
    "FailureReason",
    "GitCommitSha",
    "IntentSnapshot",
    "InvalidRunTransition",
    "InvalidStageOutput",
    "MethodologyAsset",
    "PlanStageResult",
    "ReviewStageResult",
    "ReviewSummary",
    "Run",
    "RunContract",
    "RunEvent",
    "RunEventType",
    "RunLifecycle",
    "RunOutcome",
    "StageResult",
    "StageStatus",
    "VerificationCheck",
    "VerificationConfig",
    "VerificationConfigSnapshot",
    "parse_stage_result",
]
