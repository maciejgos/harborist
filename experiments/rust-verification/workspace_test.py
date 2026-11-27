"""Verify that workspace defaults and same-origin capture work through Rust HTTP."""

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from compare import ROOT, fixture
from control_test import wait_for_web


def exercise(root: Path) -> None:
    repository, base, _ = fixture(root, ["test -f message.txt"])
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    tools = root / "tools"
    tools.mkdir()
    for name, script in {
        "codex": 'test "$*" = "login status"',
        "gh": 'test "$*" = "auth status --hostname github.com" || test "$*" = "api --hostname github.com repos/example/project"',
        "sbx": """case "$*" in
    '--no-input version') echo 'sbx v0.54.1' ;;
    '--no-input policy ls --json') echo '{"rules":[{"scope":"global","decision":"deny"}]}' ;;
    *) exit 1 ;;
esac""",
    }.items():
        executable = tools / name
        executable.write_text("#!/bin/sh\n" + script + "\n")
        executable.chmod(0o755)
    env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}"}
    settings = root / "settings.yaml"
    settings.write_text("""version: 1
playbook: {name: bounded-repository-change, version: '1', path: /opt/harborist/src/harborist/playbooks/bounded-repository-change.md}
skills: []
agent_profile: {name: local-codex, version: '1', provider: codex, model: initial, arguments: []}
sandbox_policy: trusted-local
""")
    binary = ROOT / "target/release/harborist-verify"
    control = root / "control"
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"

    def request(path: str, payload=None, *, same_origin=True):
        message = urllib.request.Request(
            origin + "/api" + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Origin": origin if same_origin else "http://untrusted.invalid",
                "Content-Type": "application/json", "X-Harborist-Workspace": "1",
            },
        )
        with urllib.request.urlopen(message, timeout=5) as response:
            return json.load(response)

    with (
        subprocess.Popen([binary, "service", control], env=env) as service,
        subprocess.Popen([binary, "web", control, str(port)]) as web,
    ):
        try:
            deadline = time.monotonic() + 5
            while not (control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            wait_for_web(port, web)
            with urllib.request.urlopen(origin + "/integrations", timeout=5) as page:
                assert b"<title>Harborist" in page.read()
            defaults = {
                "repository": str(repository), "ref": base,
                "timeout": 90, "verification_reserve": 20,
            }
            workspace = {"id": str(uuid.uuid4()), "name": "Example", **defaults}
            try:
                request("/workspaces", workspace, same_origin=False)
            except urllib.error.HTTPError as error:
                assert error.code == 403
            else:
                raise AssertionError("cross-origin write accepted")
            assert request("/workspaces") == {"workspaces": []}
            saved = request("/workspaces", workspace)
            assert saved["id"] == workspace["id"]
            assert request("/workspaces") == {"workspaces": [saved]}

            integrations_workspace = request("/workspaces", {
                **workspace, "id": str(uuid.uuid4()), "name": "Integrations",
                "settings": str(settings), "github_repository": "example/project",
            })
            workspace_id = integrations_workspace["id"]
            assert request("/integrations/codex/check", {})["status"] == "ready"
            assert request("/integrations/github", {"workspace_id": workspace_id})["status"] == "connected"
            assert request("/integrations/sandbox/check", {})["status"] == "ready"
            profile_route = f"/integrations/codex/profile/{workspace_id}"
            policy_route = f"/integrations/sandbox/policy/{workspace_id}"
            assert request(profile_route)["model"] == "initial"
            assert request(profile_route, {"model": "updated", "effort": "high"}) == {"status": "saved"}
            assert request(profile_route)["effort"] == "high"
            assert request(policy_route)["policy"] == "trusted-local"
            policy = {"kind": "docker-sandboxes", "allow": [" EXAMPLE.COM "], "baseline_sha256": "a" * 64}
            try:
                request(policy_route, {"policy": policy}, same_origin=False)
            except urllib.error.HTTPError as error:
                assert error.code == 403
            else:
                raise AssertionError("cross-origin policy write accepted")
            assert request(policy_route, {"policy": policy}) == {"status": "saved"}
            stored = request(policy_route)["policy"]
            assert stored["allow"] == ["example.com"] and stored["baseline_sha256"] is None
            assert request(profile_route)["model"] == "updated"

            payload = {"request_id": str(uuid.uuid4()), "source": str(intent), **defaults}
            queued = request("/workspace/runs", payload)
            assert queued["run_id"] == payload["request_id"]
            assert request("/workspace/runs", payload) == queued
            assert len(request("/runs")["runs"]) == 1
            path = control / "runs" / queued["run_id"] / "contract.json"
            capture = json.loads(path.read_text())
            assert capture["total_seconds"] == 90
            assert capture["verification_reserve_seconds"] == 20
            try:
                request("/workspace/runs", {**payload, "timeout": 100})
            except urllib.error.HTTPError as error:
                assert error.code == 400
            else:
                raise AssertionError("request ID accepted conflicting inputs")
        finally:
            web.terminate()
            service.terminate()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust browser Workspace and capture checks passed.")
