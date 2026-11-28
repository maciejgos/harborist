"""Read an unmodified Python Run through the Rust control service."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from compare import ROOT, fixture, git
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
    args = [
        "--json", "--repo", str(repo), "--ref", base, "--settings", str(settings),
        "--runs-dir", str(runs),
    ]
    result = subprocess.run([
        sys.executable, "-m", "harborist", "run", f"file:{intent}", "--foreground",
        *args, "--workspace", str(root / "workspace"),
    ], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    directory = next(runs.iterdir())
    evidence = json.loads((directory / "evidence.json").read_text())
    run_id = evidence["run"]["run_id"]
    before = (directory / "run.json").read_bytes()
    journal = (directory / "events.jsonl").read_bytes()
    binary = ROOT / "target/release/harborist-verify"
    public = root / "harborist"
    public.symlink_to(binary)
    inspection = ["inspect", run_id, "--runs-dir", str(runs)]
    python_contract = json.loads(subprocess.check_output(
        [sys.executable, "-m", "harborist", *inspection], env=env,
    ))
    assert json.loads(subprocess.check_output([public, *inspection], env=env)) == python_contract
    methodology = ["methodology", run_id, "--runs-dir", str(runs)]
    for stage in ([], ["--stage", "design"], ["--stage", "review"]):
        python_preview = json.loads(subprocess.check_output(
            [sys.executable, "-m", "harborist", *methodology, *stage], env=env,
        ))
        rust_preview = json.loads(subprocess.check_output([public, *methodology, *stage], env=env))
        assert rust_preview == python_preview
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
            log_route = f"{route}/attempts/0/artifacts/test-0000-stdout"
            log = directory / "test/logs/0000.stdout.log"
            original_log = log.read_bytes()
            assert client.request("GET", log_route)["content"] == original_log.decode()
            log.write_bytes(original_log + b"tampered")
            try:
                client.request("GET", log_route)
            except ValueError as error:
                assert "digest" in str(error)
            else:
                raise AssertionError("tampered historical TEST log was served")
            finally:
                log.write_bytes(original_log)
            report = client.request("GET", f"{route}/attempts/0/artifacts/report.md")
            assert report["content"] == (directory / "report.md").read_text()
            (directory / "events.jsonl").write_text("")
            invalid = client.request("GET", route)
            assert invalid["run"] is None and invalid.get("candidate_sha") is None
        finally:
            service.terminate()
    assert (directory / "run.json").read_bytes() == before


    (directory / "events.jsonl").write_bytes(journal)
    git(repo, "branch", "legacy-delivery", base)
    log = directory / "test/logs/0000.stdout.log"
    frozen_log = log.read_bytes()
    log.write_bytes(frozen_log + b"tampered")
    command = [binary, "apply", directory, "legacy-delivery"]
    refused = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert refused.returncode != 0 and "digest" in refused.stderr
    assert git(repo, "rev-parse", "legacy-delivery") == base
    log.write_bytes(frozen_log)
    package_path = directory / "evidence.json"
    package_bytes = package_path.read_bytes()
    spec_path = directory / "design/spec.md"
    original_spec = spec_path.read_bytes()
    changed_spec = original_spec + b"\nChanged after DESIGN.\n"
    spec_path.write_bytes(changed_spec)
    spec_entry = next(entry for entry in evidence["files"] if entry["path"] == "design/spec.md")
    spec_entry.update(size_bytes=len(changed_spec), sha256=hashlib.sha256(changed_spec).hexdigest())
    package_path.write_text(json.dumps(evidence))
    refused = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert refused.returncode != 0 and "does not match DESIGN" in refused.stderr, refused.stderr
    assert git(repo, "rev-parse", "legacy-delivery") == base
    spec_path.write_bytes(original_spec)
    package_path.write_bytes(package_bytes)
    receipt = json.loads(subprocess.check_output(command, env=env))
    assert receipt["resulting_sha"] == evidence["candidate"]["candidate_sha"]
    assert git(repo, "rev-parse", "legacy-delivery") == receipt["resulting_sha"]
    assert (directory / "run.json").read_bytes() == before

    remote = root / "remote.git"
    subprocess.check_call(["git", "init", "--bare", "-q", remote])
    git(repo, "push", str(remote), f"{base}:refs/heads/main")
    git(repo, "config", f"url.{remote}.insteadOf", "https://github.com/example/project.git")
    (root / "gh").write_text("""#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["PR_STATE"])
if "?" in args[3]:
    print("[" + state.read_text() + "]" if state.exists() else "[]")
else:
    fields = dict(arg.split("=", 1) for arg in args if "=" in arg)
    branch = fields["head"]
    sha = subprocess.check_output([
        "git", "--git-dir", os.environ["TEST_REMOTE"], "rev-parse", "refs/heads/" + branch,
    ], text=True).strip()
    state.write_text(json.dumps({
        "number": 1, "html_url": "https://github.com/example/project/pull/1", "state": "open",
        "head": {"ref": branch, "sha": sha}, "base": {"ref": fields["base"], "sha": sha},
    }))
    print(state.read_text())
""")
    (root / "gh").chmod(0o755)
    env.update({"PR_STATE": str(root / "pull.json"), "TEST_REMOTE": str(remote)})
    publish = [binary, "publish", directory, receipt["resulting_sha"], "example/project", "main"]
    url = subprocess.check_output(publish, env=env, text=True).strip()
    assert url == "https://github.com/example/project/pull/1"
    assert subprocess.check_output(publish, env=env, text=True).strip() == url
    assert git(remote, "rev-parse", f"refs/heads/harborist/{run_id}") == receipt["resulting_sha"]
    assert (directory / "run.json").read_bytes() == before

    native_records = runs / "rust-publications" / run_id
    [completed] = native_records.glob("published-*.json")
    saved = json.loads(completed.read_text())
    approval = saved["approval"]
    historical_records = runs / "publications" / run_id
    historical_records.mkdir(parents=True)
    prepared = {**approval, "repository": approval["destination"],
                "timestamp": "2026-01-01T00:00:00Z", "pull": None}
    prepared.pop("destination")
    (historical_records / f"prepared-{approval['attempt']}.json").write_text(
        json.dumps(prepared)
    )
    historical_receipt = historical_records / "published-000000.json"
    historical_receipt.write_text(json.dumps({**prepared, "pull": saved["pull"]}))
    historical_bytes = historical_receipt.read_bytes()
    completed.unlink()
    (native_records / f"prepared-{approval['attempt']}.json").unlink()
    assert subprocess.check_output(publish, env=env, text=True).strip() == url
    assert historical_receipt.read_bytes() == historical_bytes
    assert not list(native_records.glob("published-*.json"))

    rejected = subprocess.run(
        [binary, "import-python", directory, root / "rejected"], env=env,
        capture_output=True, text=True, check=False,
    )
    assert rejected.returncode != 0 and not (root / "rejected").exists()
    subprocess.check_call(
        [sys.executable, "-m", "harborist", "intake", f"file:{intent}", *args], env=env,
    )
    original = next(path for path in runs.iterdir() if path != directory and (path / "contract.json").is_file())
    contract_bytes = (original / "contract.json").read_bytes()
    settings_bytes = settings.read_bytes()
    settings.unlink()
    intent.unlink()
    exported = root / "imported"
    subprocess.check_call([binary, "import-python", original, exported], env=env)
    outcome = json.loads(subprocess.check_output([binary, "execute", exported], env=env))
    expected = json.loads(contract_bytes)
    assert outcome["outcome"] == "VERIFIED" and outcome["run_id"] == expected["run_id"]
    assert outcome["base_sha"] == expected["base_sha"]
    assert (original / "contract.json").read_bytes() == contract_bytes
    assert json.loads((original / "run.json").read_text())["lifecycle"] == "CREATED"

    (repo / "harborist.yaml").write_text(
        '{"version":1,"checks":[{"id":"fix","command":"test -f fixed"}]}'
    )
    git(repo, "add", "harborist.yaml")
    git(repo, "commit", "-qm", "Require the rework fix")
    intent.write_text("# Rework historical Run\n")
    settings.write_bytes(settings_bytes)
    failure_runs = root / "failures"
    result = subprocess.run([
        sys.executable, "-m", "harborist", "run", f"file:{intent}", "--foreground",
        "--json", "--repo", str(repo), "--ref", git(repo, "rev-parse", "HEAD"),
        "--settings", str(settings), "--runs-dir", str(failure_runs),
        "--workspace", str(root / "failure-workspace"),
    ], env=env, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    historical = next(path for path in failure_runs.iterdir() if (path / "evidence.json").is_file())
    evidence_path = historical / "evidence.json"
    original_evidence = evidence_path.read_bytes()
    failed = json.loads(original_evidence)
    assert failed["run"]["outcome"] == "TEST_FAILED", result.stderr
    (root / "codex").write_text(FAKE_CODEX.replace(
        'if stage == "build":', 'if stage == "build":\n    Path("fixed").touch()',
    ))
    destination = root / "continued"
    command = [binary, "continue-python", "rework", historical, destination,
               failed["attempt"]["attempt_id"], "Address the failed check"]
    outcome = json.loads(subprocess.check_output(command, env=env))
    assert outcome["outcome"] == "VERIFIED"
    assert outcome["run_id"] == failed["run"]["run_id"]
    new_attempt = destination / "attempts/000001"
    assert (new_attempt / "design/spec.md").read_bytes() == (historical / "design/spec.md").read_bytes()
    assert outcome["attempt"]["start_sha"] == failed["candidate"]["candidate_sha"]
    assert evidence_path.read_bytes() == original_evidence

    recovery_runs = root / "recovery-runs"
    fixed_codex = (root / "codex").read_text()
    (root / "codex").write_text("#!/bin/sh\nexit 1\n")
    failed_execution = subprocess.run([
        sys.executable, "-m", "harborist", "run", f"file:{intent}", "--foreground",
        "--json", "--repo", str(repo), "--ref", git(repo, "rev-parse", "HEAD"),
        "--settings", str(settings), "--runs-dir", str(recovery_runs),
        "--workspace", str(root / "recovery-workspace"),
    ], env=env, capture_output=True, text=True, check=False)
    assert failed_execution.returncode != 0
    interrupted = next(path for path in recovery_runs.iterdir() if (path / "evidence.json").is_file())
    failure = json.loads((interrupted / "evidence.json").read_bytes())
    assert failure["run"]["failure_reason"] == "EXECUTION_FAILED", failed_execution.stderr
    (root / "codex").write_text(fixed_codex)
    recovered = json.loads(subprocess.check_output([
        binary, "continue-python", "recover", interrupted, root / "recovered",
        failure["attempt"]["attempt_id"], "Retry execution", "60",
    ], env=env))
    assert recovered["outcome"] == "VERIFIED"
    assert recovered["attempt"]["start_sha"] == failure["attempt"]["start_sha"]

    queue_control = root / "historical-control"
    queued_destination = root / "queued-historical"
    queued = json.loads(subprocess.check_output([
        binary, "submit-python-continuation", queue_control, "rework", historical,
        queued_destination, failed["attempt"]["attempt_id"], "Address the failed check",
    ], env=env))
    assert queued["state"] == "queued"
    assert not queued_destination.exists()
    subprocess.check_call([binary, "worker", queue_control, "--once"], env=env)
    queued_package = queued_destination / "attempts/000001/evidence.json"
    assert json.loads(queued_package.read_bytes())["outcome"] == "VERIFIED"
    delivery = queue_control / "queue" / f"{failed['run']['run_id']}.json"
    assert json.loads(delivery.read_bytes())["state"] == "finished"
    assert evidence_path.read_bytes() == original_evidence

    cancel_control = root / "historical-cancel-control"
    cancelled_destination = root / "cancelled-historical"
    subprocess.check_call([
        binary, "submit-python-continuation", cancel_control, "rework", historical,
        cancelled_destination, failed["attempt"]["attempt_id"], "Address the failed check",
    ], env=env)
    with subprocess.Popen([binary, "service", cancel_control], env=env) as service:
        try:
            deadline = time.monotonic() + 5
            while not (cancel_control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            client = ControlClient(cancel_control)
            route = f"/workspace/runs/{failed['run']['run_id']}/cancel"
            request = {"reason": "Operator cancelled the historical rework"}
            cancellation = client.request("POST", route, request)
            assert client.request("POST", route, request) == cancellation
            subprocess.check_call([binary, "worker", cancel_control, "--once"], env=env)
            assert client.request("GET", f"/runs/{failed['run']['run_id']}")["state"] == "CANCELLED"
            assert not cancelled_destination.exists()
            assert evidence_path.read_bytes() == original_evidence
        finally:
            service.terminate()

    evidence_path.unlink()
    interrupted_destination = root / "continued-interruption"
    interrupted_command = [
        binary, "continue-python", "recover", historical, interrupted_destination,
        failed["attempt"]["attempt_id"], "Recover interrupted execution",
    ]
    refused = subprocess.run(interrupted_command, check=False, env=env, capture_output=True, text=True)
    assert refused.returncode != 0 and "explicit" in refused.stderr
    assert not interrupted_destination.exists()
    spec_path = historical / "design/spec.md"
    durable_spec = spec_path.read_bytes()
    spec_path.write_bytes(durable_spec + b"tampered")
    refused = subprocess.run([*interrupted_command, "600"], check=False, env=env, capture_output=True, text=True)
    assert refused.returncode != 0 and "digest" in refused.stderr
    assert not interrupted_destination.exists()
    spec_path.write_bytes(durable_spec)
    recovered = json.loads(subprocess.check_output([*interrupted_command, "600"], env=env))
    assert recovered["attempt"]["start_sha"] == failed["attempt"]["start_sha"]
    assert recovered["outcome"] == "VERIFIED"
    assert (interrupted_destination / "attempts/000001/design/spec.md").read_bytes() == durable_spec


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust legacy history checks passed.")
