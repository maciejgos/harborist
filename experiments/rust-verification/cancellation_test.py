"""Check queued and active cancellation through the Rust control service."""
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from compare import ROOT, fixture
from foreground_test import FAKE_CODEX

from harborist.control.client import ControlClient


def wait_for(predicate, timeout=8):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end
        time.sleep(0.02)


def exercise(root: Path) -> None:
    started = root / "test-started"
    repo, base, _ = fixture(root, [f"touch {started}; sleep 30"])
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    (root / "codex").write_text(FAKE_CODEX)
    (root / "codex").chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations")}
    binary = ROOT / "target/release/harborist-verify"
    control = root / "control"

    def enroll(directory):
        contract = json.loads(subprocess.check_output(
            [binary, "intake", repo, base, intent, directory], env=env,
        ))
        subprocess.check_call([binary, "submit", control, directory], env=env)
        return contract["run_id"]

    queued = root / "queued"
    first = enroll(queued)
    active = root / "active"
    second = enroll(active)
    with subprocess.Popen([binary, "service", control], env=env) as service:
        try:
            wait_for((control / "service.sock").exists)
            client = ControlClient(control)
            request = {"reason": "Operator stopped the Run"}
            route = f"/workspace/runs/{first}/cancel"
            response = client.request("POST", route, request)
            assert response == client.request("POST", route, request)
            with subprocess.Popen([binary, "worker", control], env=env) as worker:
                try:
                    wait_for(started.exists)
                    client.request("POST", f"/workspace/runs/{second}/cancel", request)
                    wait_for((active / "evidence.json").exists)
                    evidence = json.loads((active / "evidence.json").read_text())
                    assert evidence["outcome"] == "CANCELLED"
                    assert evidence["receipts"][-2]["stage"] == "test"
                    assert evidence["receipts"][-2]["outcome"] == "cancelled"
                    assert "review" not in (root / "invocations").read_text()
                    assert not (queued / "attempt.json").exists()
                    assert client.request("GET", f"/runs/{first}")["state"] == "CANCELLED"
                    assert client.request("GET", f"/runs/{second}")["run"]["lifecycle"] == "CANCELLED"
                finally:
                    worker.terminate()
            original = root / "original"
            old_id = enroll(original)
            new_id = str(uuid.uuid4())
            route = f"/workspace/runs/{old_id}/supersede"
            payload = {
                "reason": "Corrected request",
                "request_id": new_id,
                "source": str(root / "missing.md"),
                "repository": str(repo),
                "ref": base,
            }
            try:
                client.request("POST", route, payload)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid replacement was accepted")
            assert not (original / "retirement.json").exists()
            (root / "missing.md").write_text("Replacement request")
            result = client.request("POST", route, payload)
            assert result["replacement"] == new_id
            assert client.request("POST", route, payload) == result
            assert client.request("GET", f"/runs/{old_id}")["state"] == "CANCELLED"
            assert client.request("GET", f"/runs/{new_id}")["state"] == "QUEUED"
            try:
                client.request("POST", route, {**payload, "reason": "Different reason"})
            except ValueError:
                pass
            else:
                raise AssertionError("supersession reason changed on retry")

        finally:
            service.terminate()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust queued and active cancellation checks passed.")
