"""Exercise frozen execution settings and trusted-local policy selection."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from compare import ROOT, fixture
from foreground_test import FAKE_CODEX


def exercise(root: Path) -> None:
    repo, base, _ = fixture(root, ["test -f message.txt"])
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    assets = Path("/opt/harborist/src/harborist")
    playbook = root / "playbook.md"
    skill = root / "skill.md"
    shutil.copyfile(assets / "playbooks/bounded-repository-change.md", playbook)
    shutil.copyfile(assets / "skills/engineering.md", skill)
    settings = repo / "harborist.settings.yaml"
    text = (
        "version: 1\n"
        f"playbook: {{name: bounded-repository-change, version: '1', path: {playbook}}}\n"
        f"skills: [{{name: engineering, version: '2', path: {skill}}}]\n"
        "agent_profile:\n  name: local\n  version: '1'\n  provider: codex\n"
        "  model: recorded-model\n  arguments: ['-c', 'model_reasoning_effort=\"medium\"']\n"
        "sandbox_policy: trusted-local\n"
    )
    settings.write_text(text)
    codex = root / "codex"
    codex.write_text(FAKE_CODEX.replace(
        'stage = request["stage"]',
        'stage = request["stage"]\n'
        'assert args[args.index("--model") + 1] == "recorded-model"\n'
        'assert \'model_reasoning_effort="medium"\' in args\n'
        'assert "canonical order" in request["guidance"]["playbook"]\n'
        'assert "Use spec.md" in request["guidance"]["skills"][0]\n'
        'if stage == "review":\n'
        '    assert "build-process.json" in dict(request["inputs"])',
    ).replace(
        '"process_report": None',
        '"process_report": {"checks": [], "limitations": "fixture"} if stage == "build" else None',
    ))
    codex.chmod(0o755)
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "INVOCATIONS": str(root / "invocations")}
    binary = ROOT / "target/release/harborist-verify"
    saved = root / "saved"

    settings.write_text(text.replace("trusted-local", "{kind: docker-sandboxes}"))
    result = subprocess.run(
        [binary, "intake", repo, base, intent, saved], env=env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0 and "sandbox" in result.stderr, result.stderr
    assert not saved.exists()
    settings.write_text(text)
    contract = json.loads(subprocess.check_output([binary, "intake", repo, base, intent, saved], env=env))
    assert contract["execution"]["profile"]["model"] == "recorded-model"
    settings.unlink()
    playbook.unlink()
    skill.unlink()
    result = subprocess.run([binary, "execute", saved], env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["outcome"] == "VERIFIED"
    development = json.loads((saved / "build/build-process.json").read_text())
    assert development["provenance"] == "agent-reported"
    assert development["run_id"] == contract["run_id"]


def sandbox_fingerprint(root: Path) -> None:
    from harborist.sandbox.docker import policy_digest

    binary = ROOT / "target/release/harborist-verify"
    snapshot = root / "policy.json"
    rules = [
        {"scope": "global", "decision": "allow", "resources": ["example.org:443"],
         "reason": "café 🔒", "id": "display"},
        {"scope": "global", "decision": "deny", "resource_type": "network"},
        {"scope": "sandbox", "decision": "allow", "resources": ["other.org"]},
    ]
    command = [binary, "sandbox-policy-digest", snapshot]

    def compare() -> str:
        raw = json.dumps({"rules": rules}).encode()
        snapshot.write_bytes(raw)
        actual = subprocess.check_output(command, text=True).strip()
        assert actual == policy_digest(raw)
        return actual

    expected = compare()
    rules[0]["id"] = "changed"
    rules.reverse()
    assert compare() == expected
    rules[-1]["resources"] = ["different.org:443"]
    assert compare() != expected
    snapshot.write_text('{"rules":[]}')
    result = subprocess.run(command, capture_output=True, check=False)
    assert result.returncode != 0 and not result.stdout


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
        sandbox_fingerprint(Path(directory))
    print("Rust frozen execution settings checks passed.")
