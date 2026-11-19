import pytest

from harborist.github.collaboration import Feedback, select_feedback


def test_selection_only_uses_explicit_feedback() -> None:
    records = (
        Feedback(key="review:1", author="a", body="Selected"),
        Feedback(key="comment:2", author="b", body="Excluded"),
    )
    assert select_feedback(records, ["review:1"]) == "[review:1] a\nSelected"
    with pytest.raises(ValueError, match="Unknown"):
        select_feedback(records, ["review:3"])
