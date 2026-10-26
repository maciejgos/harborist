"""Canonical routing uses trusted receipts; it does not execute stages."""

import pytest
from pydantic import ValidationError

from shipyard.domain import ArtifactStage, Attempt, Candidate, Run
from shipyard.domain.playbook import canonical_playbook
from shipyard.domain.playbook_execution import (
    InvalidPlaybookTransition,
    PlaybookExecution,
    StageReceipt,
    StepOutcome,
)


def execution() -> PlaybookExecution:
    return PlaybookExecution(
        playbook=canonical_playbook(version="1"),
        attempt=Attempt.create(Run.create().run_id, "a" * 40),
    )


def through_build() -> PlaybookExecution:
    state = execution()
    for stage in (ArtifactStage.INTAKE, ArtifactStage.DESIGN, ArtifactStage.PLAN):
        state = state.accept(StageReceipt(stage=stage, outcome=StepOutcome.SUCCEEDED))
    return state.accept(
        StageReceipt(
            stage=ArtifactStage.BUILD,
            outcome=StepOutcome.SUCCEEDED,
            candidate=state.attempt.create_candidate("b" * 40),
        )
    )


def test_successful_execution_requires_every_stage_and_round_trips() -> None:
    state = through_build()
    candidate = state.candidate
    for stage in (ArtifactStage.TEST, ArtifactStage.REVIEW, ArtifactStage.PACKAGE):
        assert state.next_stage is not None and state.next_stage.stage == stage
        state = state.accept(
            StageReceipt(
                stage=stage,
                outcome=StepOutcome.SUCCEEDED,
                candidate=candidate if stage != ArtifactStage.PACKAGE else None,
            )
        )
    assert state.next_stage is None
    assert tuple(receipt.stage for receipt in state.receipts) == tuple(ArtifactStage)
    assert PlaybookExecution.model_validate_json(state.model_dump_json()) == state
    with pytest.raises(InvalidPlaybookTransition):
        state.accept(
            StageReceipt(stage=ArtifactStage.INTAKE, outcome=StepOutcome.SUCCEEDED)
        )


def test_cannot_skip_test_or_erase_it_in_rehydrated_history() -> None:
    state = through_build()
    review = StageReceipt(
        stage=ArtifactStage.REVIEW,
        outcome=StepOutcome.SUCCEEDED,
        candidate=state.candidate,
    )
    with pytest.raises(InvalidPlaybookTransition):
        state.accept(review)
    with pytest.raises(ValidationError):
        PlaybookExecution.model_validate(
            {**state.model_dump(), "receipts": [*state.receipts, review]}
        )
    assert state.next_stage is not None and state.next_stage.stage == ArtifactStage.TEST


def test_failed_test_blocks_review_and_cannot_be_replaced_by_success() -> None:
    state = through_build()
    state = state.accept(
        StageReceipt(
            stage=ArtifactStage.TEST,
            outcome=StepOutcome.TEST_FAILED,
            candidate=state.candidate,
        )
    )
    assert (
        state.next_stage is not None and state.next_stage.stage == ArtifactStage.PACKAGE
    )
    for stage in (ArtifactStage.REVIEW, ArtifactStage.TEST):
        with pytest.raises(InvalidPlaybookTransition):
            state.accept(
                StageReceipt(
                    stage=stage,
                    outcome=StepOutcome.SUCCEEDED,
                    candidate=state.candidate,
                )
            )
    finished = state.accept(
        StageReceipt(stage=ArtifactStage.PACKAGE, outcome=StepOutcome.FAILED)
    )
    assert finished.next_stage is None


@pytest.mark.parametrize("stage", [ArtifactStage.TEST, ArtifactStage.REVIEW])
def test_candidate_drift_is_rejected(stage: ArtifactStage) -> None:
    state = through_build()
    if stage == ArtifactStage.REVIEW:
        state = state.accept(
            StageReceipt(
                stage=ArtifactStage.TEST,
                outcome=StepOutcome.SUCCEEDED,
                candidate=state.candidate,
            )
        )
    different = Candidate(attempt_id=state.attempt.attempt_id, candidate_sha="c" * 40)
    with pytest.raises(InvalidPlaybookTransition, match="Candidate"):
        state.accept(
            StageReceipt(
                stage=stage, outcome=StepOutcome.SUCCEEDED, candidate=different
            )
        )


def test_build_candidate_must_belong_to_current_attempt() -> None:
    state = through_build()
    before_build = PlaybookExecution(
        playbook=state.playbook, attempt=state.attempt, receipts=state.receipts[:-1]
    )
    other = Attempt.create(state.attempt.run_id, "a" * 40).create_candidate("b" * 40)
    with pytest.raises(InvalidPlaybookTransition, match="Attempt"):
        before_build.accept(
            StageReceipt(
                stage=ArtifactStage.BUILD,
                outcome=StepOutcome.SUCCEEDED,
                candidate=other,
            )
        )


@pytest.mark.parametrize(
    "outcome",
    [StepOutcome.NEEDS_CLARIFICATION, StepOutcome.FAILED, StepOutcome.CANCELLED],
)
def test_early_exit_still_requires_package(outcome: StepOutcome) -> None:
    state = execution().accept(
        StageReceipt(stage=ArtifactStage.INTAKE, outcome=StepOutcome.SUCCEEDED)
    )
    state = state.accept(StageReceipt(stage=ArtifactStage.DESIGN, outcome=outcome))
    assert (
        state.next_stage is not None and state.next_stage.stage == ArtifactStage.PACKAGE
    )
    assert not state.next_stage.budgeted
    with pytest.raises(InvalidPlaybookTransition):
        state.accept(
            StageReceipt(stage=ArtifactStage.PLAN, outcome=StepOutcome.SUCCEEDED)
        )


def test_wrong_outcome_and_missing_candidate_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StageReceipt(stage=ArtifactStage.TEST, outcome=StepOutcome.NEEDS_CLARIFICATION)
    with pytest.raises(ValidationError):
        StageReceipt(stage=ArtifactStage.BUILD, outcome=StepOutcome.SUCCEEDED)
    with pytest.raises(ValidationError):
        StageReceipt(stage=ArtifactStage.PACKAGE, outcome=StepOutcome.CANCELLED)


@pytest.mark.parametrize(
    "stage,outcome",
    [
        (ArtifactStage.PLAN, StepOutcome.NEEDS_RESCOPING),
        (ArtifactStage.REVIEW, StepOutcome.CHANGES_REQUIRED),
    ],
)
def test_stage_specific_stops_route_to_package(
    stage: ArtifactStage, outcome: StepOutcome
) -> None:
    state = through_build()
    if stage == ArtifactStage.PLAN:
        state = PlaybookExecution(
            playbook=state.playbook, attempt=state.attempt, receipts=state.receipts[:2]
        )
    else:
        state = state.accept(
            StageReceipt(
                stage=ArtifactStage.TEST,
                outcome=StepOutcome.SUCCEEDED,
                candidate=state.candidate,
            )
        )
    state = state.accept(
        StageReceipt(
            stage=stage,
            outcome=outcome,
            candidate=state.candidate if stage == ArtifactStage.REVIEW else None,
        )
    )
    assert (
        state.next_stage is not None and state.next_stage.stage == ArtifactStage.PACKAGE
    )
