import json
from pathlib import Path

import pytest

from harborist.agents.base import AgentExecutionError
from harborist.domain.sandbox import SandboxPolicy
from harborist.sandbox.docker import DockerSandboxRuntime, policy_digest
from tests.git_helpers import git, init_repository


def test_global_policy_digest_ignores_display_ids_but_detects_authority_changes() -> (
    None
):
    import json

    rules = [
        {
            "id": "one",
            "scope": "global",
            "decision": "allow",
            "resources": ["pypi.org:443"],
        }
    ]
    before = policy_digest(json.dumps({"rules": rules}).encode())
    rules[0]["id"] = "other"
    assert policy_digest(json.dumps({"rules": rules}).encode()) == before
    rules[0]["decision"] = "deny"
    assert policy_digest(json.dumps({"rules": rules}).encode()) != before


def test_changed_baseline_prevents_provisioning_and_host_execution(
    tmp_path: Path,
) -> None:
    class Runtime(DockerSandboxRuntime):
        def baseline_digest(self) -> str:
            return "b" * 64

        def control(self, *args: str, timeout: float = 10) -> bytes:
            pytest.fail("No sandbox should be provisioned or removed")

    repo = tmp_path / "repo"
    init_repository(repo)
    git(repo, "commit", "--allow-empty", "-m", "base")
    with (
        pytest.raises(AgentExecutionError, match="changed since intake"),
        Runtime().workspace(
            policy=SandboxPolicy(baseline_sha256="a" * 64),
            workspace=repo,
            seconds=10,
            label="build",
            receipts=tmp_path / "receipts",
        ),
    ):
        pytest.fail("Must not admit model execution")


def test_cancellation_still_stops_only_the_owned_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harborist.execution.cancellation import cancellation_check
    from harborist.sandbox.docker import DockerWorkspace

    calls: list[tuple[str, ...]] = []

    class Runtime(DockerSandboxRuntime):
        def control(self, *args: str, timeout: float = 10) -> bytes:
            assert cancellation_check.get() is None
            calls.append(args)
            return (
                json.dumps([{"name": name, "status": "stopped"}]).encode()
                if args[0] == "ls"
                else b""
            )

    def ready(self: DockerWorkspace) -> None:
        self.started = True

    monkeypatch.setattr(DockerWorkspace, "prepare", ready)
    repo = tmp_path / "repo"
    init_repository(repo)
    git(repo, "commit", "--allow-empty", "-m", "base")
    token = cancellation_check.set(lambda: True)
    name = ""
    try:
        with (
            pytest.raises(KeyboardInterrupt),
            Runtime().workspace(
                policy=SandboxPolicy(),
                workspace=repo,
                seconds=10,
                label="build",
                receipts=tmp_path / "receipts",
            ) as guest,
        ):
            name = guest.name
            raise KeyboardInterrupt
        assert calls == [("stop", name), ("ls", "--json")]
        receipt = json.loads((tmp_path / "receipts" / f"{name}.json").read_text())
        assert receipt["retained"]
        assert not receipt["removed"]
    finally:
        cancellation_check.reset(token)


def test_verification_commands_use_supplied_executor(tmp_path: Path) -> None:
    from harborist.domain.verification import VerificationCheck, VerificationConfig
    from harborist.execution.process import ProcessCapture
    from harborist.verification.runner import run_checks

    commands: list[list[str]] = []

    def sandbox(
        command: list[str], *, cwd: Path, timeout: float, limit: int
    ) -> ProcessCapture:
        commands.append(command)
        return ProcessCapture(7, False, b"sandbox output", b"", False, False)

    config = VerificationConfig(
        version=1,
        checks=(VerificationCheck(id="test", command="must-not-execute-on-host"),),
    )
    result = run_checks(
        config=config,
        workspace=tmp_path,
        logs_dir=tmp_path / "logs",
        timeout_seconds=2,
        executor=sandbox,
    )
    assert not result.passed
    assert result.checks[0].returncode == 7
    assert commands == [["/bin/sh", "-c", "must-not-execute-on-host"]]
