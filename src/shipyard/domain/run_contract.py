"""A partial frozen execution contract, independent of lifecycle and I/O."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from shipyard.domain.intent import IntentSnapshot
from shipyard.domain.revision import GitCommitSha
from shipyard.domain.verification import VerificationConfigSnapshot


class RunContract(BaseModel):
    """Bind existing inputs by Run and base; declared provenance is not proof.

    Methodology, execution profile, budget, and policy fields remain future work.
    Use validated construction/deserialization rather than trusted-data bypasses.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    intent: IntentSnapshot
    base_sha: GitCommitSha
    verification: VerificationConfigSnapshot

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.intent.run_id != self.run_id:
            raise ValueError("Intent Run ownership must match contract run_id")
        if self.verification.base_sha != self.base_sha:
            raise ValueError("Verification base SHA must match contract base_sha")
        return self
