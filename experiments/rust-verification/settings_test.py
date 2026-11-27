"""Exercise frozen execution settings and trusted-local policy selection."""

import json
import os
import shutil
import subprocess
import tempfile
from threading import Thread
from pathlib import Path

from compare import ROOT, fixture, git
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
    sandbox_run = root / "sandbox-run"
    policy = root / "intake-policy.json"
    policy.write_text('{"rules":[{"scope":"global","decision":"deny"}]}')
    sandbox_env = sandbox_fixture(root, policy)
    contract = json.loads(subprocess.check_output(
        [binary, "intake", repo, base, intent, sandbox_run], env=sandbox_env,
    ))
    expected = subprocess.check_output([binary, "sandbox-check"], env=sandbox_env, text=True).strip()
    assert contract["execution"]["docker_policy"]["baseline_sha256"] == expected
    command = [binary, "execute", sandbox_run]
    result = subprocess.run(command, env=sandbox_env, capture_output=True, text=True, check=False)
    assert result.returncode != 0 and "requires the Rust sandbox runtime" in result.stderr
    policy.write_text('{"rules":[{"scope":"global","decision":"allow"}]}')
    result = subprocess.run(command, env=sandbox_env, capture_output=True, text=True, check=False)
    assert result.returncode != 0 and "changed since capture" in result.stderr
    assert not (sandbox_run / "attempt.json").exists()
    assert not (root / "invocations").exists()
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


def sandbox_fixture(root: Path, snapshot: Path) -> dict[str, str]:
    sbx = root / "sbx"
    sbx.write_text("""#!/bin/sh
case "$*" in
    '--no-input version') printf '%s\n' "$SBX_VERSION" ;;
    '--no-input policy ls --json') cat "$SBX_POLICY" ;;
    *) exit 1 ;;
esac
""")
    sbx.chmod(0o755)
    return {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "SBX_VERSION": "sbx v0.54.2", "SBX_POLICY": str(snapshot)}


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
    env = sandbox_fixture(root, snapshot)
    current = compare()
    check = [binary, "sandbox-check"]
    assert subprocess.check_output(check, env=env, text=True).strip() == current
    assert subprocess.check_output([*check, current], env=env, text=True).strip() == current
    changed = subprocess.run([*check, expected], env=env, capture_output=True)
    assert changed.returncode != 0 and b"changed since capture" in changed.stderr
    env["SBX_VERSION"] = "sbx v0.55.0"
    unsupported = subprocess.run(check, env=env, capture_output=True)
    assert unsupported.returncode != 0 and b"requires Docker Sandboxes 0.54.x" in unsupported.stderr
    snapshot.write_text('{"rules":[]}')
    result = subprocess.run(command, capture_output=True, check=False)
    assert result.returncode != 0 and not result.stdout


def sandbox_host(root: Path) -> None:
    from harborist.execution.process import ProcessCapture
    from harborist.sandbox.docker import policy_digest
    from harborist.sandbox.host_transport import create_server

    raw = b'{"rules":[{"scope":"global","decision":"deny"}]}'

    class Fixture:
        def execute(self, args, *, timeout, limit, input_bytes):
            assert timeout == 10 and limit == 1024 * 1024 and input_bytes == b""
            output = {
                ("version",): b"sbx v0.54.2",
                ("policy", "ls", "--json"): raw,
            }[args]
            return ProcessCapture(0, False, output, b"", False, False)

    token = root / "sbx-token"
    token.write_text("fixture-token")
    with create_server(Fixture(), b"fixture-token", port=0) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            binary = ROOT / "target/release/harborist-verify"
            env = {**os.environ, "HARBORIST_SANDBOX_HOST": "127.0.0.1",
                   "HARBORIST_SANDBOX_PORT": str(server.server_port),
                   "HARBORIST_SANDBOX_TOKEN_FILE": str(token)}
            command = [binary, "sandbox-check"]
            assert subprocess.check_output(command, env=env, text=True).strip() == policy_digest(raw)
            token.write_text("wrong-token")
            result = subprocess.run(command, env=env, capture_output=True, check=False)
            assert result.returncode != 0 and b"rejected the operation" in result.stderr
            assert not result.stdout
        finally:
            server.shutdown()
            worker.join()


def sandbox_provision(root: Path) -> None:
    from harborist.sandbox.docker import policy_digest

    binary = ROOT / "target/release/harborist-verify"
    sbx = root / "sbx"
    sbx.write_text("""#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path
flag, *args = sys.argv[1:]
assert flag == "--no-input"
assert "OPENAI_API_KEY" not in os.environ
with Path(os.environ["SBX_LOG"]).open("a") as stream:
    print(json.dumps(args), file=stream)
if args == ["version"]:
    print("sbx v0.54.1")
elif args == ["policy", "ls", "--json"]:
    print(os.environ["SBX_POLICY"])
elif args == ["ls", "--json"]:
    print("[]")
elif args[0] == "cp":
    heads = subprocess.check_output(["git", "bundle", "list-heads", args[1]], text=True)
    assert heads.strip() == os.environ["SBX_HEAD"] + " HEAD"
    assert args[2].endswith(":/tmp/harborist-source.bundle")
elif args[0] == "exec" and args[-2:] == ["--verify", "HEAD"]:
    print(os.environ.get("GUEST_HEAD", os.environ["SBX_HEAD"]))
elif args[:2] == ["policy", "deny"] and os.environ.get("FAIL_PROVISION"):
    sys.exit(1)
""")
    sbx.chmod(0o755)
    log = root / "sbx.log"
    raw = '{"rules":[{"scope":"global","decision":"deny"}]}'
    policy = root / "frozen-sandbox-policy.json"
    policy.write_text(json.dumps({
        "kind": "docker-sandboxes", "cpus": 4, "memory_mib": 3072,
        "allow": ["allowed.example"], "deny": ["blocked.example"],
        "baseline_sha256": policy_digest(raw.encode()),
    }))
    env = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
           "SBX_POLICY": raw, "SBX_LOG": str(log), "OPENAI_API_KEY": "fixture"}
    command = [binary, "sandbox-probe", policy]
    name = subprocess.check_output(command, env=env, text=True).strip()
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[:2] == [["version"], ["policy", "ls", "--json"]]
    assert calls[2][:-1] == [
        "create", "--name", name, "--cpus", "4", "--memory", "3072m",
        "--skills", "off", "--static-mcp", "none",
    ]
    assert "@sha256:" in calls[2][-1]
    assert calls[3:] == [
        ["policy", "allow", "network", "--sandbox", name, "allowed.example"],
        ["policy", "deny", "network", "--sandbox", name, "blocked.example"],
        ["rm", "--force", name],
        ["ls", "--json"],
    ]
    log.write_text("")
    result = subprocess.run(command, env={**env, "FAIL_PROVISION": "1"}, capture_output=True)
    assert result.returncode != 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[-2:] == [["stop", calls[2][2]], ["ls", "--json"]]

    repo = root / "repo"
    head = git(repo, "rev-parse", "HEAD")
    env["SBX_HEAD"] = head
    log.write_text("")
    name = subprocess.check_output([*command, repo], env=env, text=True).strip()
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [call[0] for call in calls[5:]] == ["cp", "exec", "exec", "exec", "exec", "rm", "ls"]
    assert calls[7][-3:] == ["checkout", "--detach", head]
    assert calls[9][:5] == ["exec", "-i", "--workdir", "/home/agent/workspace/repository", name]
    assert calls[9][-3:] == ["status", "--porcelain", "--untracked-files=all"]
    assert calls[-2] == ["rm", "--force", name]
    log.write_text("")
    result = subprocess.run([*command, repo], env={**env, "GUEST_HEAD": "wrong"}, capture_output=True)
    assert result.returncode != 0 and b"checkout does not match" in result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert calls[-2:] == [["stop", calls[2][2]], ["ls", "--json"]]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
        sandbox_fingerprint(Path(directory))
        sandbox_host(Path(directory))
        sandbox_provision(Path(directory))
    print("Rust frozen execution settings checks passed.")
