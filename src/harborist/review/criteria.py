"""Parse explicit acceptance declarations; prose has no workflow authority."""

import hashlib
import re

from harborist.domain.specification import SpecificationReference
from harborist.domain.stage_result import CriterionResult, InvalidStageOutput

_DECLARATION = re.compile(
    r"^\s{0,3}(?:#{1,6}\s+|[-*+]\s+)?"
    r"(AC-[0-9]{3,})\s*(?::|—|–| -)\s*(.*)$"
)
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")


def extract_criteria(markdown: str) -> SpecificationReference:
    """All declared AC IDs are required; fenced examples are excluded.

    This intentionally small syntax avoids guessing whether arbitrary prose or
    checklists define required criteria. DESIGN guidance specifies this contract.
    """
    ids: list[str] = []
    fence: str | None = None
    for line in markdown.splitlines():
        marker = _FENCE.match(line)
        if fence is not None:
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        match = _DECLARATION.match(line)
        if match:
            if not match[2].strip():
                raise ValueError("Criterion declarations require text")
            ids.append(match[1])
    return SpecificationReference(
        sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        criterion_ids=tuple(ids),
    )


def validate_coverage(
    spec: SpecificationReference, criteria: tuple[CriterionResult, ...]
) -> None:
    ids = [item.criterion_id for item in criteria]
    if len(ids) != len(set(ids)) or set(ids) != set(spec.criterion_ids):
        raise InvalidStageOutput("REVIEW must cover exactly the required spec criteria")
