"""Verify capture, frozen execution, and exclusive admission using real Git."""

import fcntl
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from compare import ROOT, fixture
from foreground_test import FAKE_CODEX


def exercise(root: Path) -> None:
    repo, base, _ = fixture(root, ['test "$(cat message.txt)" = "hello from candidate"'])
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    invocations = root / "invocations"
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(invocations)}
    binary = ROOT / "target/release/harborist-verify"

    def call(*args: str | Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([binary, *args], env=env, capture_output=True,
                              text=True, check=False)

    saved = root / "saved"
    result = call("intake", repo, base, intent, saved)
    assert result.returncode == 0, result.stderr
    contract = json.loads(result.stdout)
    assert not invocations.exists()
    assert contract["base_sha"] == base
    assert not (saved / "attempt.json").exists()
    intent.unlink()

    (saved / "intent.md").write_text("Modified captured intent.")
    result = call("execute", saved)
    assert result.returncode != 0 and "digest" in result.stderr
    assert not invocations.exists()
    assert not (saved / "attempt.json").exists()
    (saved / "intent.md").write_text("Write the requested message.")

    command = [binary, "execute", saved]
    with (
        subprocess.Popen(
            command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        ) as first,
        subprocess.Popen(
            command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        ) as second,
    ):
        results = [(process, process.communicate()) for process in (first, second)]
    assert sorted(process.returncode for process, _ in results) == [0, 1], results
    assert invocations.read_text().splitlines() == ["design", "plan", "build", "review"]
    evidence_bytes = (saved / "evidence.json").read_bytes()
    evidence = json.loads(evidence_bytes)
    assert evidence["outcome"] == "VERIFIED"
    assert evidence["run_id"] == contract["run_id"]
    assert evidence["candidate"]
    assert call("execute", saved).returncode != 0
    assert (saved / "evidence.json").read_bytes() == evidence_bytes


    queued = root / "queued"
    intent.write_text("Write the requested message.")
    result = call("intake", repo, base, intent, queued)
    assert result.returncode == 0, result.stderr
    run_id = json.loads(result.stdout)["run_id"]
    control = root / "control"
    result = call("submit", control, queued)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "queued"
    assert call("submit", control, queued).returncode == 0
    assert invocations.read_text().splitlines() == ["design", "plan", "build", "review"]
    with (control / "queue/worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert call("worker", control, "--once").returncode != 0
    worker = subprocess.Popen([binary, "worker", control], env=env)
    try:
        deadline = time.monotonic() + 10
        while True:
            result = call("delivery", control, run_id)
            assert result.returncode == 0, result.stderr
            state = json.loads(result.stdout)["state"]
            if state == "finished":
                break
            assert state in {"queued", "running"}, result.stdout
            assert worker.poll() is None and time.monotonic() < deadline
            time.sleep(0.05)
    finally:
        worker.terminate()
        worker.wait(timeout=5)
    assert json.loads((queued / "evidence.json").read_text())["outcome"] == "VERIFIED"
    assert call("worker", control, "--once").returncode == 0
    assert len(invocations.read_text().splitlines()) == 8


    interrupted = root / "interrupted"
    result = call("intake", repo, base, intent, interrupted)
    assert result.returncode == 0, result.stderr
    interrupted_id = json.loads(result.stdout)["run_id"]
    result = call("submit", control, interrupted)
    assert result.returncode == 0, result.stderr
    delivery = json.loads(result.stdout)
    delivery["state"] = "running"
    # Simulate the durable record left behind by an interrupted worker.
    (control / "queue" / f"{interrupted_id}.json").write_text(json.dumps(delivery))
    result = call("worker", control, "--once")
    assert result.returncode == 0, result.stderr
    result = call("delivery", control, interrupted_id)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "interrupted"
    assert not (interrupted / "attempt.json").exists()
    assert len(invocations.read_text().splitlines()) == 8


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust saved Run and worker checks passed.")
