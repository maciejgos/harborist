import hashlib

import pytest

from harborist.domain.stage_result import (
    CriterionResult,
    CriterionStatus,
    InvalidStageOutput,
)
from harborist.review.criteria import extract_criteria, validate_coverage


def test_extract_explicit_declarations_and_exact_digest() -> None:
    text = "# Spec\r\n- AC-001: First\r\n## AC-002 — Second\nAC-003: Third\n"
    spec = extract_criteria(text)
    assert spec.criterion_ids == ("AC-001", "AC-002", "AC-003")
    assert spec.sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert type(spec).model_validate_json(spec.model_dump_json()) == spec


def test_examples_and_references_are_not_declarations() -> None:
    spec = extract_criteria(
        "See AC-002: example\n```md\nAC-002: ignored\n```\n~~~\nAC-003: ignored\n~~~\nAC-001: Required"
    )
    assert spec.criterion_ids == ("AC-001",)


@pytest.mark.parametrize("text", ["", "# Spec", "AC-001:", "AC-001: One\nAC-001: Two"])
def test_invalid_spec_fails_closed(text: str) -> None:
    with pytest.raises(ValueError):
        extract_criteria(text)


@pytest.mark.parametrize(
    "ids", [("AC-001",), ("AC-001", "AC-002", "AC-003"), ("AC-001", "AC-001")]
)
def test_review_must_cover_exact_spec(ids: tuple[str, ...]) -> None:
    spec = extract_criteria("AC-001: One\nAC-002: Two")
    with pytest.raises(InvalidStageOutput):
        validate_coverage(
            spec,
            tuple(
                CriterionResult(criterion_id=id, status=CriterionStatus.PASS)
                for id in ids
            ),
        )


def test_review_order_does_not_change_coverage() -> None:
    validate_coverage(
        extract_criteria("AC-001: One\nAC-002: Two"),
        (
            CriterionResult(criterion_id="AC-002", status=CriterionStatus.UNVERIFIED),
            CriterionResult(criterion_id="AC-001", status=CriterionStatus.FAIL),
        ),
    )
