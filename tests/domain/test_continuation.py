from uuid import uuid4

import pytest

from harborist.domain.attempt import Attempt
from harborist.domain.continuation import ContinuationRequest, authorize_continuation
from harborist.domain.run import FailureReason, Run, RunOutcome


def test_rework_uses_previous_candidate_and_fresh_identity() -> None:
    run = Run.create().start().complete(RunOutcome.CHANGES_REQUIRED)
    previous = Attempt.create(run.run_id, "a" * 40)
    candidate = previous.create_candidate("b" * 40)
    request = ContinuationRequest(
        action="rework", expected_attempt_id=previous.attempt_id, feedback="Fix AC-001"
    )
    attempt = authorize_continuation(run, previous, candidate, request)
    assert attempt.run_id == run.run_id
    assert attempt.start_sha == candidate.candidate_sha
    assert attempt.attempt_id != previous.attempt_id


@pytest.mark.parametrize("reason", list(FailureReason))
def test_recovery_failure_allowlist(reason: FailureReason) -> None:
    run = Run.create().start().fail(reason)
    previous = Attempt.create(run.run_id, "a" * 40)
    request = ContinuationRequest(
        action="recover", expected_attempt_id=previous.attempt_id
    )
    if reason in {
        FailureReason.EXECUTION_FAILED,
        FailureReason.INVALID_STAGE_OUTPUT,
        FailureReason.CREDENTIAL_UNAVAILABLE,
        FailureReason.CREDENTIAL_REJECTED,
    }:
        assert (
            authorize_continuation(run, previous, None, request).start_sha
            == previous.start_sha
        )
    else:
        with pytest.raises(ValueError, match="recovery"):
            authorize_continuation(run, previous, None, request)


@pytest.mark.parametrize("state", ["rescope", "cancelled", "clarify", "running"])
def test_ineligible_states_and_stale_identity(state: str) -> None:
    run = Run.create().start()
    if state == "cancelled":
        run = run.cancel()
    elif state in {"rescope", "clarify"}:
        run = run.complete(
            RunOutcome.NEEDS_RESCOPING
            if state == "rescope"
            else RunOutcome.NEEDS_CLARIFICATION
        )
    previous = Attempt.create(run.run_id, "a" * 40)
    with pytest.raises(ValueError):
        authorize_continuation(
            run,
            previous,
            None,
            ContinuationRequest(
                action="rework", expected_attempt_id=previous.attempt_id
            ),
        )
    with pytest.raises(ValueError, match="predecessor"):
        authorize_continuation(
            run,
            previous,
            None,
            ContinuationRequest(action="recover", expected_attempt_id=uuid4()),
        )
