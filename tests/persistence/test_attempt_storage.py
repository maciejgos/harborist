from pathlib import Path

import pytest

from shipyard.application.execution import execute_run
from shipyard.domain import RunContract
from shipyard.domain.continuation import ContinuationRequest
from shipyard.persistence.continuation import prepare_continuation
from tests.application.test_run_execution import FakeAgent, capture


def test_attempt_storage_preserves_predecessor_and_rejects_stale_request(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent("changes"),
    )
    assert result.attempt is not None
    original = store.directory(contract.run_id)
    before = {
        p.relative_to(original): p.read_bytes()
        for p in original.rglob("*")
        if p.is_file()
    }
    request = ContinuationRequest(
        action="rework",
        expected_attempt_id=result.attempt.attempt_id,
        feedback="Fix AC-001",
    )
    selected, record = prepare_continuation(
        store=store, run_id=contract.run_id, request=request
    )
    assert selected.directory(contract.run_id) != original
    assert store.directory(contract.run_id) == selected.directory(contract.run_id)
    assert selected.load(contract.run_id) == contract
    assert selected.load_state(contract.run_id).verification is None
    assert result.candidate is not None
    assert record.attempt.start_sha == result.candidate.candidate_sha
    assert (
        selected.directory(contract.run_id) / "frozen-spec.md"
    ).read_text() == result.stages[0].output.artifact
    for name, raw in before.items():
        assert (original / name).read_bytes() == raw
    with pytest.raises(ValueError):
        prepare_continuation(store=store, run_id=contract.run_id, request=request)


def test_tampered_spec_cannot_be_reused(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    result = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repo,
        workspace=tmp_path / "work",
        agent=FakeAgent("changes"),
    )
    (store.directory(contract.run_id) / "design" / "spec.md").write_text(
        "AC-001: silently changed"
    )
    assert result.attempt is not None
    with pytest.raises(ValueError, match="digest"):
        prepare_continuation(
            store=store,
            run_id=contract.run_id,
            request=ContinuationRequest(
                action="rework", expected_attempt_id=result.attempt.attempt_id
            ),
        )
    assert store.selected_number(contract.run_id) == 0
