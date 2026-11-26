"""Verify a fresh Attempt reuses the frozen specification and prior candidate."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from compare import ROOT, fixture, git
from foreground_test import FAKE_CODEX


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
    initial = subprocess.run([binary, "run", repo, base, intent, directory], env=env,
                             capture_output=True, text=True, check=False)
    assert initial.returncode != 0
    first_bytes = (directory / "evidence.json").read_bytes()
    first = json.loads(first_bytes)
    assert first["outcome"] == "TEST_FAILED"
    previous = first["attempt"]["attempt_id"]
    result = subprocess.run(
        [binary, "rework", directory, previous, "Address the failing check"],
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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust rework checks passed.")
