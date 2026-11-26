"""Validate exact-revision candidate application against real Git in Docker."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from compare import ROOT, fixture, git
from foreground_test import FAKE_CODEX


def exercise(root: Path) -> None:
    repo, base, _ = fixture(root, ["test -f message.txt"])
    branch = git(repo, "branch", "--show-current")
    git(repo, "reset", "--hard", base)
    git(repo, "branch", "other", base)
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations")}
    binary = ROOT / "target/release/harborist-verify"

    def call(*args: str | Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [binary, *args], env=env, capture_output=True, text=True, check=False,
        )

    run = root / "run"
    result = call("run", repo, base, intent, run)
    assert result.returncode == 0, result.stderr
    evidence_bytes = (run / "evidence.json").read_bytes()
    evidence = json.loads(evidence_bytes)
    candidate, ref = evidence["candidate"], evidence["candidate_ref"]

    test_file = run / "test/evidence.json"
    test_bytes = test_file.read_bytes()
    wrong = json.loads(test_bytes)
    wrong["checks"][0]["returncode"] = 1
    test_file.write_text(json.dumps(wrong))
    result = call("apply", run, branch)
    assert result.returncode != 0 and "TEST" in result.stderr
    assert git(repo, "rev-parse", branch) == base
    test_file.write_bytes(test_bytes)

    git(repo, "update-ref", ref, base, candidate)
    result = call("apply", run, branch)
    assert result.returncode != 0 and "candidate ref" in result.stderr
    git(repo, "update-ref", ref, candidate, base)

    dirty = repo / "dirty"
    dirty.write_text("retained")
    result = call("apply", run, branch)
    assert result.returncode != 0 and "clean" in result.stderr
    assert dirty.read_text() == "retained"
    assert git(repo, "rev-parse", branch) == base
    dirty.unlink()

    result = call("apply", run, branch)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["operation"] == "advanced"
    assert receipt["resulting_sha"] == candidate
    assert git(repo, "rev-parse", branch) == candidate
    assert git(repo, "status", "--porcelain") == ""
    assert (repo / "message.txt").read_text() == "hello from candidate"
    result = call("apply", run, branch)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == receipt

    result = call("apply", run, "other")
    assert result.returncode == 0, result.stderr
    assert git(repo, "rev-parse", "other") == candidate
    assert (run / "evidence.json").read_bytes() == evidence_bytes


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust candidate application checks passed.")
