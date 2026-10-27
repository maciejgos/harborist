from decimal import Decimal

import pytest
from pydantic import ValidationError

from shipyard.agents.base import AgentResponse
from shipyard.domain.usage import Usage


def test_usage_is_optional_and_actual_charge_requires_currency() -> None:
    assert AgentResponse(returncode=0, output="{}").usage is None
    usage = Usage(input_tokens=12, output_tokens=3)
    assert usage.actual_cost is None
    with pytest.raises(ValidationError):
        Usage(actual_cost=Decimal("0.12"))
    assert Usage(actual_cost=Decimal("0.12"), currency="USD").actual_cost is not None
    with pytest.raises(ValidationError):
        Usage(input_tokens=-1)
    with pytest.raises(ValidationError):
        Usage(provider_metadata={"large": "x" * 5000})
