import json
from pathlib import Path
from uuid import uuid4

import pytest

from shipyard.control.queue import QueueStore
from shipyard.control.saved_workspaces import WorkspaceSettings
from shipyard.control.service import ControlService
from tests.application.test_run_execution import FakeAgent
from tests.git_helpers import git, init_repository
from tests.settings_helpers import write_settings


def test_app_edits_selected_workspace_policy_and_redacts_errors(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repository(root)
    settings = write_settings(root)
    (root / "shipyard.yaml").write_text(
        "version: 1\nchecks: [{id: test, command: 'true'}]\n"
    )
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    service = ControlService(
        QueueStore(tmp_path / "control"),
        agent=FakeAgent(),
        history_root=tmp_path / "runs",
    )
    workspace = service.workspaces.save(
        WorkspaceSettings(
            id=uuid4(), name="Example", repository=root, settings=settings
        )
    )
    route = f"/integrations/sandbox/policy/{workspace.id}"
    assert service.dispatch("GET", route, b"")["policy"] == "trusted-local"
    data = {
        "kind": "docker-sandboxes",
        "allow": ["pypi.org:443"],
        "deny": ["example.com"],
        "cpus": 2,
        "memory_mib": 2048,
    }
    service.dispatch("POST", route, json.dumps({"policy": data}).encode())
    policy = service.dispatch("GET", route, b"")["policy"]
    assert isinstance(policy, dict)
    assert policy["deny"] == ["example.com"]
    before = settings.read_bytes()
    with pytest.raises(ValueError) as error:
        service.dispatch(
            "POST",
            route,
            b'{"policy":{"kind":"docker-sandboxes","allow":["https://secret@example.com"]}}',
        )
    assert "secret" not in str(error.value)
    assert before == settings.read_bytes()
    with pytest.raises(ValueError):
        service.dispatch(
            "POST",
            f"/integrations/sandbox/policy/{uuid4()}",
            json.dumps({"policy": data}).encode(),
        )
