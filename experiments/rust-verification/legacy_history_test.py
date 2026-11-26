"""Read an unmodified Python Run through the Rust control service."""
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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust legacy history checks passed.")
