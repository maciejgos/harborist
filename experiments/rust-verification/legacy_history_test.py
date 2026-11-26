"""Read an unmodified Python Run through the Rust control service."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from compare import ROOT, fixture
from foreground_test import FAKE_CODEX

from harborist.control.client import ControlClient


def exercise(root: Path) -> None:
    repo, base, _ = fixture(root, ["test -f message.txt"])
    intent = root / "issue.md"
    intent.write_text("# Historical Run\n")
    (root / "codex").write_text(FAKE_CODEX)
    (root / "codex").chmod(0o755)
    canonical = Path("/opt/harborist/src/harborist")
    settings = root / "settings.yaml"
    settings.write_text(
        "version: 1\n"
        f"playbook: {{name: bounded-repository-change, version: '1', path: {canonical}/playbooks/bounded-repository-change.md}}\n"
        f"skills: [{{name: engineering, version: '2', path: {canonical}/skills/engineering.md}}]\n"
        "agent_profile: {name: local-codex, version: '1', provider: codex, model: fixture, arguments: []}\n"
        "sandbox_policy: trusted-local\n"
    )
    runs, control = root / "runs", root / "control"
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations")}
    result = subprocess.run([
        sys.executable, "-m", "harborist", "run", f"file:{intent}", "--foreground",
        "--json", "--repo", str(repo), "--ref", base, "--settings", str(settings),
        "--runs-dir", str(runs), "--workspace", str(root / "workspace"),
    ], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    directory = next(runs.iterdir())
    evidence = json.loads((directory / "evidence.json").read_text())
    run_id = evidence["run"]["run_id"]
    before = (directory / "run.json").read_bytes()
    binary = ROOT / "target/release/harborist-verify"
    with subprocess.Popen([binary, "service", control, "--runs-dir", runs], env=env) as service:
        try:
            deadline = time.monotonic() + 5
            while not (control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            client = ControlClient(control)
            [view] = client.request("GET", "/runs")["runs"]
            assert view["source"] == "saved" and view["title"] == "Historical Run"
            assert view["run"]["outcome"] == "VERIFIED"
            assert view["candidate_sha"] == evidence["candidate"]["candidate_sha"]
            route = f"/runs/{run_id}"
            assert client.request("GET", f"{route}/attempts")["attempts"] == [0]
            assert client.request("GET", f"{route}/attempts/0")["has_specification"]
            report = client.request("GET", f"{route}/attempts/0/artifacts/report.md")
            assert report["content"] == (directory / "report.md").read_text()
            (directory / "events.jsonl").write_text("")
            invalid = client.request("GET", route)
            assert invalid["run"] is None and invalid.get("candidate_sha") is None
        finally:
            service.terminate()
    assert (directory / "run.json").read_bytes() == before


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust legacy history checks passed.")
