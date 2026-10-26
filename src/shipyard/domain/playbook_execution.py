"""Pure routing of trusted harness receipts through the canonical playbook.

Receipts are declarations from the orchestrator, not evidence that an executor ran.
This module never invokes agents/checks or grants a verified software outcome.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from shipyard.domain.artifact import ArtifactStage
from shipyard.domain.attempt import Attempt
from shipyard.domain.candidate import Candidate
from shipyard.domain.playbook import PlaybookDefinition, StageDefinition


class StepOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_RESCOPING = "needs_rescoping"
    TEST_FAILED = "test_failed"
    CHANGES_REQUIRED = "changes_required"


class InvalidPlaybookTransition(ValueError):
    """A receipt would skip a dependency or change established execution identity."""


class StageReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: ArtifactStage
    outcome: StepOutcome
    candidate: Candidate | None = None

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        allowed = {StepOutcome.SUCCEEDED, StepOutcome.FAILED}
        if self.stage != ArtifactStage.PACKAGE:
            allowed.add(StepOutcome.CANCELLED)
        if self.stage in (ArtifactStage.DESIGN, ArtifactStage.BUILD):
            allowed.add(StepOutcome.NEEDS_CLARIFICATION)
        if self.stage in (ArtifactStage.PLAN, ArtifactStage.BUILD):
            allowed.add(StepOutcome.NEEDS_RESCOPING)
        if self.stage == ArtifactStage.TEST:
            allowed.add(StepOutcome.TEST_FAILED)
        if self.stage == ArtifactStage.REVIEW:
            allowed.add(StepOutcome.CHANGES_REQUIRED)
        if self.outcome not in allowed:
            raise ValueError("Outcome is not valid for this stage")
        needs_candidate = self.stage in (ArtifactStage.TEST, ArtifactStage.REVIEW) or (
            self.stage == ArtifactStage.BUILD and self.outcome == StepOutcome.SUCCEEDED
        )
        if needs_candidate != (self.candidate is not None):
            raise ValueError(
                "Candidate is required only for BUILD success and TEST/REVIEW"
            )
        return self


class PlaybookExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    playbook: PlaybookDefinition
    attempt: Attempt
    receipts: tuple[StageReceipt, ...] = ()

    def _replay(self) -> tuple[StageDefinition | None, Candidate | None]:
        stages = self.playbook.stages
        next_index = 0
        candidate: Candidate | None = None
        for receipt in self.receipts:
            if next_index == len(stages) or receipt.stage != stages[next_index].stage:
                raise ValueError("Receipt must match the next canonical stage")
            if (
                receipt.stage == ArtifactStage.BUILD
                and receipt.outcome == StepOutcome.SUCCEEDED
            ):
                if (
                    receipt.candidate is None
                    or receipt.candidate.attempt_id != self.attempt.attempt_id
                ):
                    raise ValueError("BUILD Candidate must belong to this Attempt")
                candidate = receipt.candidate
            if receipt.stage in (ArtifactStage.TEST, ArtifactStage.REVIEW) and (
                candidate is None or receipt.candidate != candidate
            ):
                raise ValueError("TEST/REVIEW Candidate must match exact BUILD Candidate")
            if receipt.stage == ArtifactStage.PACKAGE:
                next_index = len(stages)
            elif receipt.outcome != StepOutcome.SUCCEEDED:
                next_index = len(stages) - 1
            else:
                next_index += 1
        return (None if next_index == len(stages) else stages[next_index]), candidate

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        self._replay()
        return self

    @property
    def next_stage(self) -> StageDefinition | None:
        return self._replay()[0]

    @property
    def candidate(self) -> Candidate | None:
        return self._replay()[1]

    def accept(self, receipt: StageReceipt) -> Self:
        """Accept a trusted result without inferring execution facts from prose."""
        try:
            return type(self).model_validate(
                {
                    **self.model_dump(),
                    "receipts": [
                        *(item.model_dump() for item in self.receipts),
                        receipt.model_dump(),
                    ],
                }
            )
        except ValueError as error:
            raise InvalidPlaybookTransition(str(error)) from error
