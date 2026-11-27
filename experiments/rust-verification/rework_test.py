"""Verify a fresh Attempt reuses the frozen specification and prior candidate."""

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from compare import ROOT, fixture, git
from foreground_test import FAKE_CODEX

from harborist.control.client import ControlClient


def exercise(root: Path) -> None:
    repo, base, _ = fixture(root, ["test -f fixed"])
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX.replace(
        'if stage == "build":',
        '''if os.environ.get("REWORK") and stage == "plan":
    assert Path("message.txt").exists()
    inputs = dict(request["inputs"])
    assert "AC-001" in inputs["spec.md"]
    assert "Address the failing check" in inputs["continuation-context.json"]
if stage == "build" and os.environ.get("REWORK"):
    Path("fixed").touch()
if stage == "build":''',
    ))
    codex.chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations")}
    binary = ROOT / "target/release/harborist-verify"
    directory = root / "run"
    control = root / "control"
    subprocess.check_call([binary, "intake", repo, base, intent, directory], env=env)
    subprocess.check_call([binary, "submit", control, directory], env=env)
    subprocess.check_call([binary, "worker", control, "--once"], env=env)
    first_bytes = (directory / "evidence.json").read_bytes()
    first = json.loads(first_bytes)
    assert first["outcome"] == "TEST_FAILED"
    previous = first["attempt"]["attempt_id"]
    public = root / "harborist"
    public.symlink_to(binary)
    (root / first["run_id"]).symlink_to(directory, target_is_directory=True)
    result = subprocess.run(
        [public, "rework", first["run_id"], "--foreground", "--runs-dir", root, "--repo", repo, "--json", "--feedback", "Address the failing check"],
        env={**env, "REWORK": "1"}, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    second = json.loads(result.stdout)
    assert second["outcome"] == "VERIFIED"
    assert second["attempt"]["attempt_id"] != previous
    assert second["attempt"]["start_sha"] == first["candidate"]
    assert second["base_sha"] == base
    assert git(repo, "rev-parse", second["candidate"] + "^") == first["candidate"]
    assert git(repo, "rev-parse", first["candidate_ref"]) == first["candidate"]
    assert (directory / "evidence.json").read_bytes() == first_bytes
    assert (directory / "attempts/000001/design/spec.md").read_bytes() == (
        directory / "design/spec.md"
    ).read_bytes()
    assert (root / "invocations").read_text().splitlines() == [
        "design", "plan", "build", "plan", "build", "review",
    ]


    with subprocess.Popen([binary, "service", control], env=env) as service:
        try:
            deadline = time.monotonic() + 5
            while not (control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            client = ControlClient(control)
            route = f"/runs/{first['run_id']}"
            assert client.request("GET", route)["candidate_sha"] == second["candidate"]
            assert client.request("GET", f"{route}/attempts")["attempts"] == [0, 1]
            historical = client.request("GET", f"{route}/attempts/0")
            assert historical["run"]["outcome"] == "TEST_FAILED"
            latest = client.request("GET", f"{route}/attempts/1/artifacts/evidence.json")
            assert json.loads(latest["content"])["candidate"] == second["candidate"]
        finally:
            service.terminate()
    (control / "service.sock").unlink(missing_ok=True)

    queued = root / "queued-rework"
    subprocess.check_call([binary, "intake", repo, base, intent, queued], env=env)
    subprocess.check_call([binary, "submit", control, queued], env=env)
    subprocess.check_call([binary, "worker", control, "--once"], env=env)
    predecessor = json.loads((queued / "evidence.json").read_text())
    queued_id = predecessor["run_id"]
    with subprocess.Popen([binary, "service", control], env=env) as service:
        try:
            deadline = time.monotonic() + 5
            while not (control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            client = ControlClient(control)
            payload = {
                "request_id": str(uuid.uuid4()), "action": "rework",
                "expected_attempt_id": predecessor["attempt"]["attempt_id"],
                "feedback": "Address the failing check", "additional_seconds": 0,
            }
            route = f"/workspace/runs/{queued_id}/continue"
            assert client.request("POST", route, payload)["run_id"] == queued_id
            assert client.request("POST", route, payload)["run_id"] == queued_id
            assert not (queued / "attempts").exists()
            assert client.request("GET", f"/runs/{queued_id}")["state"] == "QUEUED"
            subprocess.check_call([binary, "worker", control, "--once"], env={**env, "REWORK": "1"})
            result = client.request("GET", f"/runs/{queued_id}")
            assert result["state"] == "FINISHED"
            assert result["run"]["outcome"] == "VERIFIED" and result["attempt_number"] == 1
            assert client.request("POST", route, payload)["run_id"] == queued_id
        finally:
            service.terminate()

    git(repo, "branch", "delivery", base)
    applied = subprocess.run(
        [binary, "apply", directory, "delivery"], env=env,
        capture_output=True, text=True, check=False,
    )
    assert applied.returncode == 0, applied.stderr
    assert git(repo, "rev-parse", "delivery") == second["candidate"]


def recover(root: Path) -> None:
    repo, base, _ = fixture(root, ["test -f message.txt"])
    intent = root / "issue.md"
    intent.write_text("Recover a failed execution.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX.replace(
        'if stage == "build":',
        'if stage == "plan" and not os.environ.get("RECOVER"):\n'
        '    raise SystemExit(17)\n'
        'if stage == "build":',
    ))
    codex.chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations")}
    binary = ROOT / "target/release/harborist-verify"
    directory = root / "run"
    run = subprocess.run([binary, "run", repo, base, intent, directory], env=env,
                         capture_output=True, text=True, check=False)
    assert run.returncode != 0
    raw = (directory / "evidence.json").read_bytes()
    failed = json.loads(raw)
    public = root / "harborist"
    public.symlink_to(binary)
    (root / failed["run_id"]).symlink_to(directory, target_is_directory=True)
    result = subprocess.run(
        [public, "recover", failed["run_id"], "--foreground", "--runs-dir", root, "--repo", repo, "--json"],
        env={**env, "RECOVER": "1"}, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert failed["failure_reason"] == "EXECUTION_FAILED"
    assert json.loads(result.stdout)["outcome"] == "VERIFIED"
    assert (directory / "evidence.json").read_bytes() == raw
    assert (root / "invocations").read_text().splitlines() == ["design", "plan", "build", "review"]


def recover_worker(root: Path) -> None:
    repo, base, _ = fixture(root, ["test -f message.txt"])
    intent = root / "issue.md"
    intent.write_text("Recover an interrupted execution.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX.replace(
        'if stage == "build":',
        'if stage == "plan" and not os.environ.get("RECOVER"):\n'
        '    import time\n'
        '    Path(os.environ["STARTED"]).write_text(str(os.getpid()))\n'
        '    time.sleep(30)\n'
        'if stage == "build":',
    ))
    codex.chmod(0o755)
    started = root / "started"
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations"), "STARTED": str(started)}
    binary = ROOT / "target/release/harborist-verify"
    directory, control = root / "run", root / "control"
    captured = json.loads(subprocess.check_output([binary, "intake", repo, base, intent, directory], env=env))
    subprocess.check_call([binary, "submit", control, directory], env=env)
    with subprocess.Popen([binary, "worker", control, "--once"], env=env) as worker:
        deadline = time.monotonic() + 8
        while not started.exists():
            assert worker.poll() is None and time.monotonic() < deadline
            time.sleep(0.02)
        worker.kill()
        worker.wait(timeout=5)
    subprocess.check_call([binary, "worker", control, "--once"], env=env)
    delivery = json.loads(subprocess.check_output(
        [binary, "delivery", control, captured["run_id"]], env=env,
    ))
    assert delivery["state"] == "interrupted"
    attempt = json.loads((directory / "attempt.json").read_text())
    command = [binary, "recover", directory, attempt["attempt_id"], "Resume after worker loss"]
    denied = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert denied.returncode != 0 and "additional" in denied.stderr
    result = subprocess.run(
        [*command, "360"], env={**env, "RECOVER": "1"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["outcome"] == "VERIFIED"
    assert not (directory / "evidence.json").exists()
    assert (root / "invocations").read_text().splitlines() == ["design", "plan", "build", "review"]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        recover(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        recover_worker(Path(directory))
    print("Rust rework and recovery checks passed.")
