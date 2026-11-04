"""Serialized, create-only admission of linked attempts from checked evidence."""

import fcntl
import hashlib
from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shipyard.domain import FailureReason, RunLifecycle
from shipyard.domain.attempt import Attempt
from shipyard.domain.continuation import ContinuationRequest, authorize_continuation
from shipyard.domain.stage_result import AgentStage, StageStatus
from shipyard.evidence.index import load_index
from shipyard.persistence.run import FileRunStore, RunPersistenceError


class ContinuationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: ContinuationRequest
    previous_number: int = Field(ge=0)
    attempt: Attempt
    spent_seconds: float = Field(ge=0, allow_inf_nan=False)
    granted_seconds: int = Field(ge=0)
    predecessor_digest: str | None
    spec_digest: str | None
    interrupted: bool = False


@contextmanager
def execution_lock(store: FileRunStore, run_id: UUID) -> Generator[None]:
    """One foreground or service executor/admission per Run, without waiting."""
    with (store.original_directory(run_id) / "continuation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RunPersistenceError("Run already has an active execution") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def load_continuation(store: FileRunStore, run_id: UUID) -> ContinuationRecord:
    number = store.selected_number(run_id)
    record = ContinuationRecord.model_validate_json(
        (store.directory(run_id) / "continuation.json").read_bytes()
    )
    if number != record.previous_number + 1 or record.attempt.run_id != run_id:
        raise ValueError("Invalid continuation lineage")
    previous_store = store.pinned(run_id, record.previous_number)
    previous_dir = previous_store.directory(run_id)
    previous = Attempt.model_validate_json((previous_dir / "attempt.json").read_bytes())
    previous_run = previous_store.load_state(run_id)
    candidate = None
    if record.predecessor_digest is not None:
        raw = (previous_dir / "evidence.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != record.predecessor_digest:
            raise ValueError("Predecessor evidence digest mismatch")
        from shipyard.evidence.package import RunEvidence

        evidence = RunEvidence.model_validate_json(raw)
        if evidence.attempt != previous or evidence.run != previous_run:
            raise ValueError("Predecessor evidence attribution mismatch")
        candidate = evidence.candidate
    elif record.interrupted and previous_run.lifecycle == RunLifecycle.RUNNING:
        previous_run = previous_run.fail(FailureReason.EXECUTION_FAILED)
    else:
        raise ValueError("Missing predecessor evidence")
    expected = authorize_continuation(previous_run, previous, candidate, record.request)
    if (
        expected.start_sha != record.attempt.start_sha
        or previous.attempt_id == record.attempt.attempt_id
    ):
        raise ValueError("Continuation start/identity mismatch")
    if record.spec_digest is not None:
        raw = (store.directory(run_id) / "frozen-spec.md").read_bytes()
        if hashlib.sha256(raw).hexdigest() != record.spec_digest:
            raise ValueError("Frozen spec digest mismatch")
    return record


def prepare_continuation(
    *, store: FileRunStore, run_id: UUID, request: ContinuationRequest
) -> tuple[FileRunStore, ContinuationRecord]:
    with execution_lock(store, run_id):
        previous_store = store.pinned(run_id)
        directory = previous_store.directory(run_id)
        contract = previous_store.load(run_id)
        run = previous_store.load_state(run_id)
        if run.lifecycle == RunLifecycle.CREATED:
            raise ValueError("Latest Attempt is already admitted or incomplete")
        previous = Attempt.model_validate_json(
            (directory / "attempt.json").read_bytes()
        )
        prior = (
            load_continuation(previous_store, run_id)
            if previous_store.selected_number(run_id)
            else None
        )
        granted = (prior.granted_seconds if prior else 0) + request.additional_seconds
        allowance = contract.execution.budget.total_seconds + (
            prior.granted_seconds if prior else 0
        )
        interrupted = run.lifecycle == RunLifecycle.RUNNING
        spec: bytes | None = None
        predecessor_digest = None
        candidate = None
        evidence = None
        if interrupted:
            if request.action != "recover" or request.additional_seconds < 1:
                raise ValueError(
                    "Interrupted execution requires explicit recovery with additional seconds"
                )
            run = run.fail(FailureReason.EXECUTION_FAILED)
            spent = float(allowance)
        else:
            evidence, indexed = load_index(directory)
            if (
                evidence.contract != contract
                or evidence.run != run
                or evidence.attempt != previous
            ):
                raise ValueError("Predecessor PACKAGE attribution mismatch")
            predecessor_digest = hashlib.sha256(
                (directory / "evidence.json").read_bytes()
            ).hexdigest()
            candidate = evidence.candidate
            spent = evidence.timing.original_seconds - evidence.timing.remaining_seconds
            if evidence.timing.original_seconds != allowance:
                raise ValueError("Predecessor budget does not match recorded grants")
            designs = [
                s
                for s in evidence.stages
                if s.stage == AgentStage.DESIGN
                and s.output.result.status == StageStatus.READY
            ]
            if designs:
                if (
                    len(designs) != 1
                    or designs[0].attempt_id != previous.attempt_id
                    or designs[0].run_id != run_id
                ):
                    raise ValueError("Invalid DESIGN attribution")
                spec = indexed.get("design/spec.md")
                if spec is None or spec.decode() != designs[0].output.artifact:
                    raise ValueError("Frozen spec does not match DESIGN")
            elif prior and prior.spec_digest:
                spec = indexed.get("frozen-spec.md")
                if (
                    spec is None
                    or hashlib.sha256(spec).hexdigest() != prior.spec_digest
                ):
                    raise ValueError("Missing validated frozen spec")
        attempt = authorize_continuation(run, previous, candidate, request)
        if request.action == "rework" and spec is None:
            raise ValueError("Rework requires validated frozen spec")
        if (
            allowance + request.additional_seconds - spent
            <= contract.execution.budget.verification_reserve_seconds
        ):
            raise ValueError(
                "Insufficient remaining budget; explicitly grant additional seconds"
            )
        record = ContinuationRecord(
            request=request,
            previous_number=previous_store.selected_number(run_id),
            attempt=attempt,
            spent_seconds=spent,
            granted_seconds=granted,
            predecessor_digest=predecessor_digest,
            spec_digest=hashlib.sha256(spec).hexdigest() if spec else None,
            interrupted=interrupted,
        )
        selected = store.pinned(run_id, record.previous_number + 1)
        selected.save(contract)
        target = selected.directory(run_id)
        if spec is not None:
            (target / "frozen-spec.md").write_bytes(spec)
        if not interrupted:
            assert evidence is not None
            # A bounded context document, never a resumed session or authority.
            context = {
                "feedback": request.feedback,
                "previous_candidate": candidate.model_dump(mode="json")
                if candidate
                else None,
                "previous_plan": next(
                    (
                        s.output.plan_update or s.output.artifact
                        for s in reversed(evidence.stages)
                        if s.stage in {AgentStage.PLAN, AgentStage.BUILD}
                        and (s.output.plan_update or s.output.artifact)
                    ),
                    None,
                ),
                "test": evidence.test.model_dump(mode="json")
                if evidence.test
                else None,
                "review": next(
                    (
                        s.output.model_dump(mode="json")
                        for s in evidence.stages
                        if s.stage == AgentStage.REVIEW
                    ),
                    None,
                ),
            }
            import json

            (target / "continuation-context.json").write_text(
                json.dumps(context), encoding="utf-8"
            )
        else:
            (target / "continuation-context.json").write_text(
                request.model_dump_json(), encoding="utf-8"
            )
        with (target / "continuation.json").open("x", encoding="utf-8") as output:
            output.write(record.model_dump_json())
        return selected, record
