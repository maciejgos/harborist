"""Ownership guard for application-owned message composition."""

from uuid import uuid4

import pytest

from shipyard.application.candidate_message import candidate_message
from shipyard.domain import Attempt, RunContract


def test_candidate_message_rejects_foreign_intent(frozen_contract: RunContract) -> None:
    attempt = Attempt.create(uuid4(), frozen_contract.base_sha)
    with pytest.raises(ValueError, match="same Run"):
        candidate_message(intent=frozen_contract.intent, attempt=attempt)
