"""Optional provider-reported usage; no inferred pricing."""

import json
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    input_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    output_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    cached_tokens: Annotated[int, Field(strict=True, ge=0)] | None = None
    actual_cost: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)] | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = None
    provider_metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_reporting(self) -> Self:
        if (self.actual_cost is None) != (self.currency is None):
            raise ValueError("Actual charge and currency must be reported together")
        if len(json.dumps(self.provider_metadata, allow_nan=False).encode()) > 4096:
            raise ValueError("Provider metadata exceeds 4096 bytes")
        return self
