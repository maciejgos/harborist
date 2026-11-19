from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from harborist.agents.base import NativeAgent
from harborist.application import execution
from harborist.domain import RunContract
from harborist.domain.sandbox import SandboxPolicy
from harborist.domain.stage_result import AgentStage
from harborist.execution.process import ProcessCapture
from tests.application.test_run_execution import FakeAgent, capture


@pytest.mark.parametrize("check_exit,expected", [(0, "VERIFIED"), (7, "TEST_FAILED")])
def test_frozen_policy_routes_test_into_sandbox_and_preserves_gate(
    tmp_path: Path,
    frozen_contract: RunContract,
    check_exit: int,
    expected: str,
) -> None:
    policy = SandboxPolicy(baseline_sha256="a" * 64)
    frozen_contract = frozen_contract.model_copy(
        update={
            "execution": frozen_contract.execution.model_copy(
                update={"sandbox_policy": policy}
            )
        }
    )
    store, repository, contract = capture(
        tmp_path, frozen_contract, "must-not-run-on-host"
    )
    agent = FakeAgent()
    calls: list[str] = []

    def factory(**kwargs: object) -> NativeAgent:
        assert kwargs["policy"] == policy
        (store.directory(contract.run_id) / "sandbox").mkdir()
        return agent

    class Guest:
        def capture(
            self, command: list[str], *, cwd: Path, timeout: float, limit: int
        ) -> ProcessCapture:
            assert command == ["/bin/sh", "-c", "must-not-run-on-host"]
            calls.append("check")
            return ProcessCapture(check_exit, False, b"sandbox", b"", False, False)

        def require_unchanged(self) -> None:
            calls.append("revision")

    class Runtime:
        def agent(self, *, policy: SandboxPolicy, receipts: Path) -> NativeAgent:
            return factory(policy=policy, receipts=receipts)

        @contextmanager
        def workspace(self, **kwargs: object) -> Generator[Guest]:
            assert kwargs["policy"] == policy
            calls.append("start")
            try:
                yield Guest()
            finally:
                calls.append("remove")

    result = execution.execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repository,
        agent=FakeAgent("failure"),
        runtime=Runtime(),
    )
    assert str(result.run.outcome) == expected
    assert calls == ["start", "check", "revision", "remove"]
    assert (AgentStage.REVIEW in agent.calls) == (check_exit == 0)
    assert (store.directory(contract.run_id) / "sandbox" / "candidate.bundle").is_file()
    assert store.load(contract.run_id) == contract
