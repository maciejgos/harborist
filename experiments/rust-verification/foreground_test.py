"""Exercise the Rust foreground path through the Codex process boundary."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from compare import ROOT, fixture, git

FAKE_CODEX = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
prompt = sys.stdin.read()
request = json.loads(prompt if prompt.startswith("{") else prompt[prompt.index("\\n{") + 1:])
stage = request["stage"]
assert args[0] == "exec" and "--ephemeral" in args
assert args[args.index("--sandbox") + 1] == (
    "workspace-write" if stage == "build" else "read-only"
)
result = {"stage": stage, "status": "ready"}
artifact = {
    "design": "- AC-001: The candidate contains the requested message.",
    "plan": "Write message.txt.",
    "review": "The candidate meets AC-001.",
}.get(stage)
if stage == "build":
    Path("message.txt").write_text("hello from candidate")
if stage == "review":
    assert Path("message.txt").read_text() == "hello from candidate"
    assert not Path("test-marker").exists()
    result["candidate"] = request["candidate"]
    result["criteria"] = [{"criterion_id": "AC-001", "status": "pass"}]
with open(os.environ["INVOCATIONS"], "a") as stream:
    stream.write(stage + "\\n")
output = Path(args[args.index("--output-last-message") + 1])
output.write_text(json.dumps({
    "result": result, "artifact": artifact, "plan_update": None, "process_report": None
}))
"""


def exercise(root: Path, check: str, expected: str, stages: list[str]) -> None:
    repo, base, _ = fixture(root, [check])
    (repo / ".git/info/exclude").write_text("test-marker\n")
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    invocations = root / "invocations"
    output = root / "run"
    result = subprocess.run(
        [ROOT / "target/release/harborist-verify", "run", repo, base, intent, output],
        env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
             "INVOCATIONS": str(invocations)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == (expected == "VERIFIED"), result.stderr
    evidence = json.loads((output / "evidence.json").read_text())
    assert evidence["outcome"] == expected
    assert (output / "report.md").is_file()
    assert invocations.read_text().splitlines() == stages
    assert git(repo, "rev-parse", evidence["candidate_ref"]) == evidence["candidate"]
    assert not (output / "test-workspace").exists()
    assert not (output / "review-workspace").exists()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, check, outcome, stages in [
            ("success", 'test "$(cat message.txt)" = "hello from candidate" && touch test-marker',
             "VERIFIED", ["design", "plan", "build", "review"]),
            ("failure", "exit 7", "TEST_FAILED", ["design", "plan", "build"]),
            ("mutation", "printf changed > message.txt", "TEST_FAILED",
             ["design", "plan", "build"]),
            ("hidden-mutation", "git update-index --assume-unchanged message.txt && printf changed > message.txt",
             "TEST_FAILED", ["design", "plan", "build"]),
        ]:
            folder = root / name
            folder.mkdir()
            exercise(folder, check, outcome, stages)
        print("Rust foreground checks passed for VERIFIED and TEST_FAILED.")
