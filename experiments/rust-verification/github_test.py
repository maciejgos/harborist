"""Exercise frozen GitHub Issue intake through an offline GitHub CLI fixture."""

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from compare import ROOT, fixture

from harborist.control.client import ControlClient


def exercise(root: Path) -> None:
    repository, base, _ = fixture(root, ["test -f message.txt"])
    binary = ROOT / "target/release/harborist-verify"
    gh = root / "gh"
    issue = {
        "title": "Pinned issue",
        "body": "Build the fix.",
        "labels": [{"name": "bug"}, {"name": "bug"}, {"name": "agent"}],
        "url": "https://github.com/example/project/issues/7",
    }
    listed = {key: issue[key] for key in ("title", "labels", "url")}
    listed["number"] = 7
    gh.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "if sys.argv[2] == 'view':\n"
        "    assert sys.argv[1:] == ['issue','view','7','--repo','example/project',"
        "'--json','title,body,labels,url']\n"
        f"    print({json.dumps(issue)!r})\n"
        "else:\n"
        "    assert sys.argv[1:] == ['issue','list','--repo','example/project',"
        "'--state','open','--limit','100','--json','number,title,labels,url']\n"
        f"    print({json.dumps([listed])!r})\n"
    )
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}"}
    directory = root / "captured"
    result = subprocess.run(
        [binary, "intake", repository, base, "github:example/project#7", directory],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    contract = json.loads(result.stdout)
    assert contract["source_ref"] == "github:example/project#7"
    assert contract["source_url"] == issue["url"]
    assert (directory / "intent.md").read_text() == (
        '# Pinned issue\n\nLabels: ["agent","bug"]\n\nBuild the fix.'
    )


    control = root / "control"
    public = root / "harborist"
    public.symlink_to(binary)
    with subprocess.Popen([binary, "service", control], env=env) as service:
        try:
            deadline = time.monotonic() + 5
            while not (control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            client = ControlClient(control)
            workspace = client.request("POST", "/workspaces", {
                "id": str(uuid.uuid4()), "name": "Example",
                "repository": str(repository), "ref": base,
            })
            listing = client.request("POST", "/tickets/list", {"repository": "example/project"})
            ticket = listing["issues"][0]
            assert ticket["identity"] == "example/project#7" and ticket["labels"] == ["agent", "bug"]
            for action in ("list", "refresh"):
                result = subprocess.check_output(
                    [public, "tickets", action, "example/project", "--control-dir", control],
                    env=env, text=True,
                )
                assert result.strip() == "example/project#7\tPinned issue\tLabels: agent, bug"
            request = {
                "request_id": str(uuid.uuid4()), "workspace_id": workspace["id"],
                "source": ticket["identity"],
            }
            queued_id = subprocess.check_output([
                public, "tickets", "queue", request["source"], "--workspace", request["workspace_id"],
                "--request-id", request["request_id"], "--control-dir", control,
            ], env=env, text=True).strip()
            assert queued_id == request["request_id"]
            queued = client.request("POST", "/tickets/queue", request)
            assert client.request("POST", "/tickets/queue", request) == queued
            found = client.request("GET", f"/runs/{queued['run_id']}")
            assert found["source_url"] == issue["url"]
            assert found["title"] == "Pinned issue"
        finally:
            service.terminate()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust GitHub Issue intake checks passed.")
