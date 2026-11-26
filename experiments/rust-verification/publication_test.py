"""Exercise real Git publication and fixture PR creation without networking."""

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
    repo, base, _ = fixture(root, ["test -f message.txt"])
    remote = root / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", remote], check=True)
    git(repo, "push", str(remote), f"{base}:refs/heads/main")
    git(repo, "config", f"url.{remote}.insteadOf", "https://github.com/example/project.git")
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    (root / "codex").write_text(FAKE_CODEX)
    (root / "codex").chmod(0o755)
    (root / "gh").write_text("""#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
assert args[:3] == ["api", "--hostname", "github.com"]
state = Path(os.environ["PR_STATE"])
if args[3].startswith("repos/example/project/pulls?"):
    print("[" + state.read_text() + "]" if state.exists() else "[]")
elif args[3] == "repos/example/project/pulls/7":
    pull = json.loads(state.read_text())
    pull.update(merged=False, merged_at=None, merge_commit_sha=None)
    print(json.dumps(pull))
elif "/check-runs?" in args[3]:
    print(json.dumps({"total_count": 1, "check_runs": [
        {"name": "ci", "status": "completed", "conclusion": "success", "details_url": None}
    ]}))
elif "/status?" in args[3]:
    print(json.dumps({"state": "success", "total_count": 0, "statuses": []}))
elif args[3].endswith("?per_page=50"):
    feedback = [{"id": 9, "user": {"login": "reviewer"}, "body": "Please add a test."}]
    print(json.dumps(feedback if "/reviews?" in args[3] else []))
else:
    assert args[3] == "repos/example/project/pulls" and "--method" in args
    fields = dict(value.split("=", 1) for value in args[4:] if "=" in value)
    branch = fields["head"]
    sha = subprocess.check_output([
        "git", "--git-dir", os.environ["TEST_REMOTE"], "rev-parse", "refs/heads/" + branch
    ], text=True).strip()
    pull = {
        "number": 7, "html_url": "https://github.com/example/project/pull/7", "state": "open",
        "head": {"ref": branch, "sha": sha}, "base": {"ref": fields["base"], "sha": sha},
    }
    state.write_text(json.dumps(pull))
    print(state.read_text())
""")
    (root / "gh").chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations"), "TEST_REMOTE": str(remote),
           "PR_STATE": str(root / "pull.json")}
    binary = ROOT / "target/release/harborist-verify"
    directory = root / "run"
    control = root / "control"
    subprocess.check_call([binary, "intake", repo, base, intent, directory], env=env)
    subprocess.check_call([binary, "submit", control, directory], env=env)
    subprocess.check_call([binary, "worker", control, "--once"], env=env)
    evidence = json.loads((directory / "evidence.json").read_text())

    def publish(sha: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [binary, "publish", directory, sha, "example/project", "main"],
            env=env, text=True, capture_output=True, check=False,
        )

    wrong = publish(base)
    assert wrong.returncode != 0 and "approval" in wrong.stderr.lower()
    assert not (root / "pull.json").exists()
    approval = evidence["candidate"]
    branch = f"harborist/{evidence['run_id']}"
    unrelated = git(repo, "rev-parse", "HEAD")
    git(repo, "push", str(remote), f"{unrelated}:refs/heads/{branch}")
    result = publish(approval)
    assert result.returncode != 0 and "head" in result.stderr.lower()
    git(repo, "push", str(remote), f":refs/heads/{branch}")
    result = publish(approval)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "https://github.com/example/project/pull/7"
    assert git(remote, "rev-parse", f"refs/heads/{branch}") == approval
    assert publish(approval).stdout == result.stdout
    assert len(list((directory / "publication").glob("published-*.json"))) == 1


    with subprocess.Popen([binary, "service", control], env=env) as service:
        try:
            deadline = time.monotonic() + 5
            while not (control / "service.sock").exists():
                assert service.poll() is None and time.monotonic() < deadline
                time.sleep(0.02)
            client = ControlClient(control)
            run_id = evidence["run_id"]
            state = client.request("GET", f"/runs/{run_id}/github")
            assert state["publication"]["candidate"] == approval
            assert state["publication"]["pull"] == 7
            payload = {
                "approve": approval, "expected_attempt": evidence["attempt"]["attempt_id"],
                "destination": "example/project", "base": "main", "expect_head": approval,
            }
            route = f"/workspace/runs/{run_id}/publish"
            try:
                client.request("POST", route, {**payload, "expected_attempt": str(uuid.uuid4())})
            except ValueError as error:
                assert "different Attempt" in str(error)
            else:
                raise AssertionError("approval for another Attempt accepted")
            assert client.request("POST", route, payload)["pull"]["number"] == 7
            observed = client.request("POST", f"/workspace/runs/{run_id}/observe", {})
            snapshot = observed["observation"]
            assert snapshot["head"] == approval and snapshot["head_verified"]
            assert snapshot["checks"]["check_runs"][0]["name"] == "ci"
            assert snapshot["feedback"] == [
                {"key": "review:9", "author": "reviewer", "body": "Please add a test."}
            ]
            assert client.request("GET", f"/runs/{run_id}/github")["observation"] == snapshot
            pull_path = root / "pull.json"
            changed = json.loads(pull_path.read_text())
            changed["head"]["sha"] = unrelated
            pull_path.write_text(json.dumps(changed))
            latest = client.request("POST", f"/workspace/runs/{run_id}/observe", {})
            assert latest["observation"]["head"] == unrelated
            assert not latest["observation"]["head_verified"]
            assert latest["observation"]["verified_candidate"] == approval
            assert observed["observation_path"] != latest["observation_path"]
        finally:
            service.terminate()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust GitHub publication checks passed.")
