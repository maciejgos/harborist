"""Serialized, create-only admission of linked attempts from checked evidence."""

import fcntl
import hashlib
import json
import os
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
    context_digest: str
    interrupted: bool = False


@contextmanager
def execution_lock(store: FileRunStore, run_id: UUID) -> Generator[None]:
    """One foreground or service executor/admission per Run, without waiting."""
    descriptor = os.open(store.original_directory(run_id), os.O_RDONLY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RunPersistenceError("Run already has an active execution") from error
        yield
    finally:
        os.close(descriptor)


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
    prior = (
        load_continuation(previous_store, run_id) if record.previous_number else None
    )
    contract = store.pinned(run_id, 0).load(run_id)
    allowance = contract.execution.budget.total_seconds + (
        prior.granted_seconds if prior else 0
    )
    if (
        record.granted_seconds
        != (prior.granted_seconds if prior else 0) + record.request.additional_seconds
    ):
        raise ValueError("Continuation grant does not match explicit authorization")
    expected_spent = float(allowance)
    expected_spec = prior.spec_digest if prior else None
    if record.predecessor_digest is not None:
        raw = (previous_dir / "evidence.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != record.predecessor_digest:
            raise ValueError("Predecessor evidence digest mismatch")
        from shipyard.evidence.package import RunEvidence

        evidence = RunEvidence.model_validate_json(raw)
        if evidence.attempt != previous or evidence.run != previous_run:
            raise ValueError("Predecessor evidence attribution mismatch")
        candidate = evidence.candidate
        if (
            evidence.contract != contract
            or evidence.timing.original_seconds != allowance
        ):
            raise ValueError("Predecessor frozen contract/budget mismatch")
        expected_spent = (
            evidence.timing.original_seconds - evidence.timing.remaining_seconds
        )
        designs = [
            stage
            for stage in evidence.stages
            if stage.stage == AgentStage.DESIGN
            and stage.output.result.status == StageStatus.READY
        ]
        if designs:
            if len(designs) != 1 or designs[0].output.artifact is None:
                raise ValueError("Invalid predecessor DESIGN")
            expected_spec = hashlib.sha256(
                designs[0].output.artifact.encode()
            ).hexdigest()
    elif record.interrupted and record.request.additional_seconds > 0:
        if previous_run.lifecycle == RunLifecycle.RUNNING:
            previous_run = previous_run.fail(FailureReason.EXECUTION_FAILED)
        expected_spec = None
    else:
        raise ValueError("Missing predecessor evidence")
    if record.spent_seconds != expected_spent or record.spec_digest != expected_spec:
        raise ValueError("Continuation spending/spec provenance mismatch")
    context_raw = (store.directory(run_id) / "continuation-context.json").read_bytes()
    if (
        len(context_raw) > 524288
        or hashlib.sha256(context_raw).hexdigest() != record.context_digest
    ):
        raise ValueError("Continuation context digest/size mismatch")
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
        interrupted = (
            run.lifecycle == RunLifecycle.RUNNING
            or not (directory / "evidence.json").exists()
        )
        spec: bytes | None = None
        predecessor_digest = None
        candidate = None
        evidence = None
        if interrupted:
            if request.action != "recover" or request.additional_seconds < 1:
                raise ValueError(
                    "Interrupted execution requires explicit recovery with additional seconds"
                )
            if run.lifecycle == RunLifecycle.RUNNING:
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
        # Bound optional history, keeping the full original evidence at its locator.
        context = {
            "policy": "The supplied spec is frozen. Plan fixes against it. If feedback requires changing acceptance criteria, return needs_rescoping; a new Run is required.",
            "feedback": request.feedback,
            "previous_candidate": candidate.model_dump(mode="json")
            if candidate
            else None,
            "previous_evidence": str(directory / "evidence.json") if evidence else None,
            "previous_plan": next(
                (
                    (stage.output.plan_update or stage.output.artifact or "")[:32768]
                    for stage in reversed(evidence.stages)
                    if stage.stage in {AgentStage.PLAN, AgentStage.BUILD}
                    and (stage.output.plan_update or stage.output.artifact)
                ),
                None,
            )
            if evidence
            else None,
            "test": [
                {"id": check.id, "passed": check.passed, "returncode": check.returncode}
                for check in evidence.test.collection.checks[:128]
            ]
            if evidence and evidence.test
            else None,
            "review": next(
                (
                    (stage.output.artifact or "")[:32768]
                    for stage in evidence.stages
                    if stage.stage == AgentStage.REVIEW
                ),
                None,
            )
            if evidence
            else None,
        }
        context_raw = json.dumps(context, ensure_ascii=False).encode("utf-8")
        if len(context_raw) > 524288:
            raise ValueError("Continuation context exceeds bounded input limit")
        record = ContinuationRecord(
            request=request,
            previous_number=previous_store.selected_number(run_id),
            attempt=attempt,
            spent_seconds=spent,
            granted_seconds=granted,
            predecessor_digest=predecessor_digest,
            spec_digest=hashlib.sha256(spec).hexdigest() if spec else None,
            context_digest=hashlib.sha256(context_raw).hexdigest(),
            interrupted=interrupted,
        )
        selected = store.pinned(run_id, record.previous_number + 1)
        selected.save(contract)
        target = selected.directory(run_id)
        if spec is not None:
            (target / "frozen-spec.md").write_bytes(spec)
        (target / "continuation-context.json").write_bytes(context_raw)
        with (target / "continuation.json").open("x", encoding="utf-8") as output:
            output.write(record.model_dump_json())
        return selected, record
