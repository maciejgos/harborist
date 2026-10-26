"""Synchronous intake orchestration, stopping at a durable CREATED Run."""

from shipyard.domain import ExecutionSnapshot, Run, RunContract, RunLifecycle
from shipyard.git import GitRepository
from shipyard.intake import capture_intent
from shipyard.persistence import FileRunStore
from shipyard.skills import compile_methodology
from shipyard.verification import load_verification_config


def create_run(
    *,
    source: str,
    repository: GitRepository,
    store: FileRunStore,
    execution: ExecutionSnapshot,
    run: Run | None = None,
    ref: str = "HEAD",
) -> RunContract:
    """Resolve once, capture once, then persist without invoking any executor."""
    run = Run.create() if run is None else Run.model_validate(run.model_dump())
    if run.lifecycle != RunLifecycle.CREATED:
        raise ValueError("Intake requires a CREATED Run")
    execution = ExecutionSnapshot.model_validate(execution.model_dump())
    compile_methodology(execution)
    base_sha = repository.resolve_base(ref=ref)
    verification = load_verification_config(repository=repository, base_sha=base_sha)
    intent = capture_intent(run_id=run.run_id, source=source)
    contract = RunContract(
        run_id=run.run_id,
        intent=intent,
        base_sha=base_sha,
        verification=verification,
        execution=execution,
    )
    store.save(contract)
    return contract
