"""Check fallback against committed verification configuration."""
import json
import subprocess
import tempfile
from pathlib import Path

from compare import ROOT, fixture, git


def exercise(root: Path) -> None:
    repo, _, _ = fixture(root, ["true"])
    config = '{"version":1,"checks":[{"id":"legacy","command":"true"}]}'
    (repo / "harborist.yaml").unlink()
    (repo / "shipyard.yaml").write_text(config)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "Legacy verification config")
    base = git(repo, "rev-parse", "HEAD")
    intent = root / "issue.md"
    intent.write_text("Read the frozen checks.")
    binary = ROOT / "target/release/harborist-verify"
    result = subprocess.run(
        [binary, "intake", repo, base, intent, root / "saved"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["base_sha"] == base
    assert (root / "saved/harborist.yaml").read_text() == config

    (repo / "harborist.yaml").write_text("version: invalid")
    git(repo, "add", "harborist.yaml")
    git(repo, "commit", "-m", "Invalid primary verification config")
    result = subprocess.run(
        [binary, "intake", repo, git(repo, "rev-parse", "HEAD"), intent, root / "rejected"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert not (root / "rejected").exists()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
    print("Rust legacy configuration checks passed.")
