"""Compose candidate traceability from frozen intake provenance."""

from shipyard.domain.attempt import Attempt
from shipyard.domain.intent import IntentSnapshot


def candidate_message(*, intent: IntentSnapshot, attempt: Attempt) -> str:
    """Use the validated intake selector, independently of prose and checkout."""
    if intent.run_id != attempt.run_id:
        raise ValueError("Intent and Attempt must belong to the same Run")
    subject = "Shipyard candidate"
    if intent.source_ref.startswith("github:"):
        subject += f" for {intent.source_ref.removeprefix('github:')}"
    return f"{subject}\n\nRun: {attempt.run_id}\nAttempt: {attempt.attempt_id}"
