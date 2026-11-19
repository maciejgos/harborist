from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from harborist.configuration.execution import (
    configure_sandbox_policy,
    load_execution_settings,
    sandbox_policy_status,
)
from harborist.domain.sandbox import SandboxPolicy
from tests.settings_helpers import write_settings


def test_policy_edit_is_atomic_and_future_runs_only(tmp_path: Path) -> None:
    path = write_settings(tmp_path)
    original = load_execution_settings(path=path)
    before = yaml.safe_load(path.read_text())
    policy = SandboxPolicy(allow=("api.example.com:443",), deny=("example.com",))
    configure_sandbox_policy(path, policy)
    saved = sandbox_policy_status(path)
    assert saved["policy"] == policy.model_dump(mode="json")
    after = yaml.safe_load(path.read_text())
    assert after["agent_profile"] == before["agent_profile"]
    assert original.sandbox_policy == "trusted-local"
    configure_sandbox_policy(path, "trusted-local")
    assert load_execution_settings(path=path) == original


@pytest.mark.parametrize(
    "resource",
    ["https://secret@example.com", "--cloud", "a,b", "a\nb", "**", "localhost:99999"],
)
def test_network_rules_reject_unsafe_or_overbroad_values(resource: str) -> None:
    with pytest.raises(ValidationError):
        SandboxPolicy(allow=(resource,))


def test_policy_freezes_docker_baseline_at_intake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harborist.sandbox.docker import DockerSandboxRuntime

    path = write_settings(tmp_path)
    configure_sandbox_policy(path, SandboxPolicy())

    def baseline(self: DockerSandboxRuntime) -> str:
        return "a" * 64

    monkeypatch.setattr(DockerSandboxRuntime, "baseline_digest", baseline)
    frozen = load_execution_settings(path=path)
    assert isinstance(frozen.sandbox_policy, SandboxPolicy)
    assert frozen.sandbox_policy.baseline_sha256 == "a" * 64
    assert yaml.safe_load(path.read_text())["sandbox_policy"]["baseline_sha256"] is None


def test_conflicting_network_rules_fail_before_save() -> None:
    with pytest.raises(ValidationError):
        SandboxPolicy(allow=("example.com",), deny=("example.com",))
