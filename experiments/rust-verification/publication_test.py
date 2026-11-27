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
    (root / "codex").write_text(FAKE_CODEX.replace(
        'if stage == "build":',
        'if stage == "plan" and os.environ.get("FEEDBACK"):\n'
        '    context = json.loads(dict(request["inputs"])["continuation-context.json"])\n'
        '    assert "Please add a test." in context["feedback"]\n'
        '    assert context["previous_candidate"] == os.environ["LOCAL_CANDIDATE"]\n'
        'if stage == "build":',
    ))
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
    if state.exists():
        pull = json.loads(state.read_text())
        if pull.get("follow_remote"):
            pull["head"]["sha"] = subprocess.check_output([
                "git", "--git-dir", os.environ["TEST_REMOTE"], "rev-parse",
                "refs/heads/" + pull["head"]["ref"],
            ], text=True).strip()
        print(json.dumps([pull]))
    else:
        print("[]")
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
elif args[3] == "repos/example/project/issues/7/comments":
    comments = state.with_name("comments.json")
    written = json.loads(comments.read_text()) if comments.exists() else []
    if "--method" in args:
        body = next(value.removeprefix("body=") for value in args if value.startswith("body="))
        written.append({"body": body})
        comments.write_text(json.dumps(written))
        print(json.dumps(written[-1]))
    else:
        print(json.dumps([written]))
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
    control = root / ".harborist" / "control"
    env["HOME"] = str(root)
    public = root / "harborist"
    public.symlink_to(binary)
    subprocess.check_call([binary, "intake", repo, base, intent, directory], env=env)
    subprocess.check_call([binary, "submit", control, directory], env=env)
    subprocess.check_call([binary, "worker", control, "--once"], env=env)
    evidence = json.loads((directory / "evidence.json").read_text())

    def publish(sha: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [public, "publish", evidence["run_id"], "--approve", sha,
             "--destination", "example/project", "--base", "main"],
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
            continuation = {
                "request_id": str(uuid.uuid4()), "action": "rework",
                "expected_attempt_id": evidence["attempt"]["attempt_id"],
                "github_feedback": {"observation": latest["observation_path"],
                                    "ids": ["review:9", "review:9"]},
            }
            action = f"/workspace/runs/{run_id}/continue"
            try:
                client.request("POST", action, {
                    **continuation,
                    "github_feedback": {"observation": latest["observation_path"], "ids": ["review:999"]},
                })
            except ValueError as error:
                assert "feedback ID" in str(error)
            else:
                raise AssertionError("unknown feedback accepted")
            assert client.request("POST", action, continuation)["run_id"] == run_id
            subprocess.check_call(
                [binary, "worker", control, "--once"],
                env={**env, "FEEDBACK": "1", "LOCAL_CANDIDATE": approval},
            )
            newest = client.request("GET", f"/runs/{run_id}")
            assert newest["run"]["outcome"] == "VERIFIED"
            assert newest["attempt_number"] == 1
            record = json.loads((directory / "attempts/000001/continuation.json").read_text())
            assert record["context"]["feedback"].count("Please add a test.") == 1
            assert record["attempt"]["start_sha"] == approval

            previous = client.request("GET", f"/runs/{run_id}/github")["publication"]
            assert previous["candidate"] == approval
            updated = {
                **payload, "approve": newest["candidate_sha"],
                "expected_attempt": newest["attempt_id"], "expect_head": approval,
            }
            try:
                client.request("POST", route, {**updated, "expect_head": unrelated})
            except ValueError as error:
                assert "expected head" in str(error)
            else:
                raise AssertionError("incorrect expected remote head accepted")
            pull_path.write_text(json.dumps({**changed, "follow_remote": True}))
            assert client.request("POST", route, updated)["pull"]["number"] == 7
            assert git(remote, "rev-parse", f"refs/heads/{branch}") == newest["candidate_sha"]
            assert client.request("POST", route, {**updated, "expect_head": newest["candidate_sha"]})["pull"]["number"] == 7
            comments = json.loads((root / "comments.json").read_text())
            assert len(comments) == 1 and newest["candidate_sha"] in comments[0]["body"]
            receipt = client.request("GET", f"/runs/{run_id}/github")["publication"]
            assert receipt["candidate"] == newest["candidate_sha"] and receipt["previous"] == approval

        finally:
            service.terminate()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust GitHub publication checks passed.")
