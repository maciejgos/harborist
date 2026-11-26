"""Exercise the Rust read API through the canonical Python control client."""

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from compare import ROOT, fixture
from foreground_test import FAKE_CODEX

from harborist.control.client import ControlClient


def exercise(root: Path) -> None:
    repo, base, _ = fixture(root, ['test -f message.txt'])
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations")}
    binary = ROOT / "target/release/harborist-verify"
    control, run = root / "control", root / "run"
    contract = json.loads(subprocess.check_output(
        [binary, "intake", repo, base, intent, run], env=env,
    ))
    run_id = contract["run_id"]
    subprocess.check_call([binary, "submit", control, run], env=env)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    with subprocess.Popen([binary, "service", control], env=env) as service:
        try:
            deadline = time.monotonic() + 5
            while not (control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            client = ControlClient(control)
            assert client.request("GET", "/health") == {"version": 1, "stopping": False}
            before = client.request("GET", "/runs")["runs"][0]
            assert before["submission"]["run_id"] == run_id
            assert before["state"] == "QUEUED" and before["run"] is None
            subprocess.check_call([binary, "worker", control, "--once"], env=env)
            after = client.request("GET", f"/runs/{run_id}")
            assert after["run"]["outcome"] == "VERIFIED"
            assert after["candidate_sha"] == json.loads(
                (run / "evidence.json").read_text()
            )["candidate"]
            artifact = client.request("GET", f"/runs/{run_id}/artifacts/report.md")
            assert artifact["content"] == (run / "report.md").read_text()
            assert client.request("GET", f"/runs/{run_id}/attempts") == {"attempts": [0]}
            attempt = client.request("GET", f"/runs/{run_id}/attempts/0")
            assert attempt["has_specification"]
            assert attempt["stages"]["review"]["state"] == "completed"
            spec = client.request("GET", f"/runs/{run_id}/attempts/0/artifacts/spec.md")
            assert "AC-001" in spec["content"]
            log = client.request("GET", f"/runs/{run_id}/attempts/0/artifacts/test-0000-stdout")
            assert log["content"] == ""
            with subprocess.Popen([binary, "web", control, str(port)], env=env) as web:
                try:
                    wait_for_web(port, web)
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/runs") as response:
                        assert json.load(response)["runs"][0]["run"]["outcome"] == "VERIFIED"
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/runs", headers={"Host": "untrusted.invalid"},
                    )
                    try:
                        urllib.request.urlopen(request)
                    except urllib.error.HTTPError as error:
                        assert error.code == 403
                    else:
                        raise AssertionError("unexpected non-loopback Host acceptance")
                finally:
                    web.terminate()
        finally:
            service.terminate()


def wait_for_web(port: int, web: subprocess.Popen) -> None:
    deadline = time.monotonic() + 5
    while True:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
                assert "Harborist" in response.read().decode()
            return
        except urllib.error.URLError:
            assert web.poll() is None and time.monotonic() < deadline
            time.sleep(0.02)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust control API and loopback browser checks passed.")
