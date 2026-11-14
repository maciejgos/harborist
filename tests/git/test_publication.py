import pytest

from shipyard.git.publication import expected_head


def test_stale_head_cannot_be_replaced() -> None:
    with pytest.raises(ValueError, match="head changed"):
        expected_head(observed="human", previous="published", candidate="verified")


def test_partial_publication_can_be_reconciled() -> None:
    assert expected_head(
        observed="verified", previous="published", candidate="verified"
    )
    assert not expected_head(observed=None, previous=None, candidate="verified")
