"""Exercise real Git publication and fixture PR creation without networking."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from compare import ROOT, fixture, git
from foreground_test import FAKE_CODEX


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
    evidence = json.loads(subprocess.check_output([binary, "run", repo, base, intent, directory], env=env))

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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust GitHub publication checks passed.")
