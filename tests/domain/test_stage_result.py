"""Acceptance tests for native-agent declarations, without execution authority."""

import json
from itertools import product
from uuid import UUID

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from shipyard.domain import (
    AgentStage,
    BuildStageResult,
    Candidate,
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

MODELS: dict[AgentStage, type[BaseModel]] = {
    AgentStage.DESIGN: DesignStageResult,
    AgentStage.PLAN: PlanStageResult,
    AgentStage.BUILD: BuildStageResult,
    AgentStage.REVIEW: ReviewStageResult,
}
ALLOWED_STATUSES = {
    AgentStage.DESIGN: {StageStatus.READY, StageStatus.NEEDS_CLARIFICATION},
    AgentStage.PLAN: {StageStatus.READY, StageStatus.NEEDS_RESCOPING},
    AgentStage.BUILD: set(StageStatus),
    AgentStage.REVIEW: {StageStatus.READY},
}
CANDIDATE = Candidate(
    attempt_id=UUID("a8bf3b18-45b7-4e17-a6ce-38ea4865a18f"),
    candidate_sha="0123456789abcdef" * 2 + "01234567",
)


def payload_for(stage: AgentStage) -> dict[str, object]:
    payload: dict[str, object] = {"stage": stage.value, "status": "ready"}
    if stage == AgentStage.REVIEW:
        payload.update(
            candidate=CANDIDATE.model_dump(mode="json"),
            criteria=[{"criterion_id": "AC-001", "status": "pass"}],
        )
    return payload


def assert_invalid(payload: object, stage: AgentStage) -> None:
    with pytest.raises(ValidationError):
        MODELS[stage].model_validate(payload)
    with pytest.raises(InvalidStageOutput) as caught:
        parse_stage_result(json.dumps(payload), stage)
    assert isinstance(caught.value.__cause__, ValidationError)


@pytest.mark.parametrize("stage,status", tuple(product(AgentStage, StageStatus)))
def test_stage_status_matrix(stage: AgentStage, status: StageStatus) -> None:
    payload = {**payload_for(stage), "status": status.value}
    if status not in ALLOWED_STATUSES[stage]:
        assert_invalid(payload, stage)
        return
    result = parse_stage_result(json.dumps(payload), stage)
    assert isinstance(result, MODELS[stage])
    assert result.stage == stage
    assert result.status == status
    assert MODELS[stage].model_validate(payload) == result
    assert parse_stage_result(result.model_dump_json(), stage) == result
    assert TypeAdapter(StageResult).validate_json(result.model_dump_json()) == result
    assert result.model_dump(mode="json") == payload


def test_direct_construction() -> None:
    assert (
        DesignStageResult(
            stage=AgentStage.DESIGN, status=StageStatus.NEEDS_CLARIFICATION
        ).stage
        == AgentStage.DESIGN
    )
    assert (
        PlanStageResult(stage=AgentStage.PLAN, status=StageStatus.NEEDS_RESCOPING).stage
        == AgentStage.PLAN
    )
    assert (
        BuildStageResult(stage=AgentStage.BUILD, status=StageStatus.READY).stage
        == AgentStage.BUILD
    )
    criterion = CriterionResult(criterion_id="AC-001", status=CriterionStatus.PASS)
    review = ReviewStageResult(
        stage=AgentStage.REVIEW,
        status=StageStatus.READY,
        candidate=CANDIDATE,
        criteria=(criterion,),
    )
    assert review.criteria == (criterion,)
    with pytest.raises(ValidationError, match="unique"):
        ReviewStageResult(
            stage=AgentStage.REVIEW,
            status=StageStatus.READY,
            candidate=CANDIDATE,
            criteria=(criterion, criterion),
        )


@pytest.mark.parametrize("stage", AgentStage)
@pytest.mark.parametrize("field", ["stage", "status"])
def test_stage_and_status_are_required(stage: AgentStage, field: str) -> None:
    payload = payload_for(stage)
    del payload[field]
    assert_invalid(payload, stage)


@pytest.mark.parametrize("stage", AgentStage)
@pytest.mark.parametrize("value", ["unknown", "READY", "", None, True, 1])
def test_unknown_status(stage: AgentStage, value: object) -> None:
    assert_invalid({**payload_for(stage), "status": value}, stage)


@pytest.mark.parametrize("value", ["test", "DESIGN", "unknown", "", None, 1])
def test_unknown_stage(value: object) -> None:
    assert_invalid({"stage": value, "status": "ready"}, AgentStage.DESIGN)


@pytest.mark.parametrize("actual,expected", tuple(product(AgentStage, AgentStage)))
def test_expected_stage(actual: AgentStage, expected: AgentStage) -> None:
    raw = json.dumps(payload_for(actual))
    if actual == expected:
        assert parse_stage_result(raw, expected).stage == actual
    else:
        with pytest.raises(InvalidStageOutput, match="Expected") as caught:
            parse_stage_result(raw, expected)
        assert caught.value.__cause__ is None


@pytest.mark.parametrize("stage", AgentStage)
@pytest.mark.parametrize("extra", ["summary", "unexpected", "verified"])
def test_extra_fields(stage: AgentStage, extra: str) -> None:
    assert_invalid({**payload_for(stage), extra: {}}, stage)


def test_build_cannot_assert_candidate() -> None:
    assert_invalid(
        {
            **payload_for(AgentStage.BUILD),
            "candidate": CANDIDATE.model_dump(mode="json"),
        },
        AgentStage.BUILD,
    )


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "",
        "null",
        "[]",
        '"ready"',
        '```json\n{"stage":"design","status":"ready"}\n```',
        'Done: {"stage":"design","status":"ready"}',
        '{"stage":"design","status":"ready"} trailing prose',
    ],
)
def test_parser_rejects_without_repair(raw: str) -> None:
    with pytest.raises(InvalidStageOutput) as caught:
        parse_stage_result(raw, AgentStage.DESIGN)
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value.__cause__, ValidationError)


@pytest.mark.parametrize("field", ["candidate", "criteria"])
def test_review_requires_assessment_fields(field: str) -> None:
    payload = payload_for(AgentStage.REVIEW)
    del payload[field]
    assert_invalid(payload, AgentStage.REVIEW)


@pytest.mark.parametrize(
    "criteria",
    [
        [],
        None,
        {},
        [None],
        [{}],
        [{"criterion_id": "AC-001"}],
        [{"status": "pass"}],
        [{"criterion_id": "AC-001", "status": "unknown"}],
        [{"criterion_id": "AC-001", "status": "PASS"}],
        [{"criterion_id": "AC-001", "status": "pass", "extra": 1}],
        [
            {"criterion_id": "AC-001", "status": "pass"},
            {"criterion_id": "AC-001", "status": "fail"},
        ],
    ],
)
def test_invalid_criteria(criteria: object) -> None:
    assert_invalid(
        {**payload_for(AgentStage.REVIEW), "criteria": criteria}, AgentStage.REVIEW
    )


@pytest.mark.parametrize(
    "criterion_id", ["", " ", " AC-1", "AC-1 ", "\tAC-1", "AC-1\n", 1, None]
)
def test_invalid_criterion_ids(criterion_id: object) -> None:
    criterion = {"criterion_id": criterion_id, "status": "pass"}
    with pytest.raises(ValidationError):
        CriterionResult.model_validate(criterion)
    assert_invalid(
        {**payload_for(AgentStage.REVIEW), "criteria": [criterion]}, AgentStage.REVIEW
    )


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        {},
        {"attempt_id": str(CANDIDATE.attempt_id)},
        {"candidate_sha": CANDIDATE.candidate_sha},
        {"attempt_id": "invalid", "candidate_sha": CANDIDATE.candidate_sha},
        {"attempt_id": str(CANDIDATE.attempt_id), "candidate_sha": "main"},
        {"attempt_id": str(CANDIDATE.attempt_id), "candidate_sha": "a" * 39},
        {**CANDIDATE.model_dump(mode="json"), "extra": True},
    ],
)
def test_invalid_review_candidate(candidate: object) -> None:
    assert_invalid(
        {**payload_for(AgentStage.REVIEW), "candidate": candidate}, AgentStage.REVIEW
    )


@pytest.mark.parametrize("length", [40, 64])
def test_review_accepts_both_hash_formats(length: int) -> None:
    candidate = {"attempt_id": str(CANDIDATE.attempt_id), "candidate_sha": "a" * length}
    result = parse_stage_result(
        json.dumps({**payload_for(AgentStage.REVIEW), "candidate": candidate}),
        AgentStage.REVIEW,
    )
    assert isinstance(result, ReviewStageResult)
    assert result.candidate.candidate_sha == "a" * length


@pytest.mark.parametrize(
    "statuses,counts",
    [
        ([CriterionStatus.PASS], (1, 0, 0)),
        ([CriterionStatus.FAIL], (0, 1, 0)),
        ([CriterionStatus.UNVERIFIED], (0, 0, 1)),
        ([*CriterionStatus, CriterionStatus.PASS], (2, 1, 1)),
    ],
)
def test_review_summary(
    statuses: list[CriterionStatus], counts: tuple[int, int, int]
) -> None:
    criteria = [
        {"criterion_id": f"AC-{index}", "status": status.value}
        for index, status in enumerate(statuses)
    ]
    payload = {**payload_for(AgentStage.REVIEW), "criteria": criteria}
    result = parse_stage_result(json.dumps(payload), AgentStage.REVIEW)
    assert isinstance(result, ReviewStageResult)
    assert result.status == StageStatus.READY
    assert isinstance(result.criteria, tuple)
    assert result.summary == ReviewSummary(
        pass_count=counts[0], fail_count=counts[1], unverified_count=counts[2]
    )
    assert "summary" not in result.model_dump()
    assert json.loads(result.model_dump_json()) == payload
    assert "summary" not in ReviewStageResult.model_json_schema()["properties"]


@pytest.mark.parametrize("field", ["pass_count", "fail_count", "unverified_count"])
@pytest.mark.parametrize("value", [-1, 1.5, "1", True, None])
def test_summary_requires_nonnegative_integers(field: str, value: object) -> None:
    data = {"pass_count": 0, "fail_count": 0, "unverified_count": 0, field: value}
    with pytest.raises(ValidationError):
        ReviewSummary.model_validate(data)


@pytest.mark.parametrize("stage", AgentStage)
def test_all_stage_and_nested_fields_are_frozen(stage: AgentStage) -> None:
    result = parse_stage_result(json.dumps(payload_for(stage)), stage)
    records: list[BaseModel] = [result]
    if isinstance(result, ReviewStageResult):
        records.extend([result.candidate, *result.criteria, result.summary])
    for record in records:
        before = record.model_dump_json()
        for field in type(record).model_fields:
            with pytest.raises(ValidationError, match="frozen"):
                setattr(record, field, getattr(record, field))
            with pytest.raises(ValidationError, match="frozen"):
                delattr(record, field)
        assert record.model_dump_json() == before


@pytest.mark.parametrize(
    "model,payload",
    [
        (CriterionResult, {"criterion_id": "AC-001", "status": "pass", "extra": 1}),
        (
            ReviewSummary,
            {"pass_count": 0, "fail_count": 0, "unverified_count": 0, "extra": 1},
        ),
    ],
)
def test_nested_models_reject_extra_fields(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate(payload)
