"""Content-bound required criterion references from an explicit specification."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class SpecificationReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    criterion_ids: Annotated[
        tuple[Annotated[str, StringConstraints(pattern=r"^AC-[0-9]{3,}$")], ...],
        Field(min_length=1),
    ]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len(set(self.criterion_ids)) != len(self.criterion_ids):
            raise ValueError("Specification criterion IDs must be unique")
        return self
