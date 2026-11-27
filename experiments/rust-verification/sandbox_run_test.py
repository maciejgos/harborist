"""Run the full Rust workflow through an offline sbx command fixture."""

import json
import os
import socket
import subprocess
import tempfile
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

from compare import ROOT, fixture, git
from foreground_test import FAKE_CODEX

FAKE_SBX = r"""#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

flag, command, *args = sys.argv[1:]
assert flag == "--no-input"
guests = Path(os.environ["FIXTURE_GUESTS"])
with Path(os.environ["SBX_HISTORY"]).open("a") as stream:
    print(json.dumps([command, *args]), file=stream)
if command == "version":
    print("sbx v0.54.1")
elif command == "policy":
    assert args == ["ls", "--json"]
    print('{"rules":[{"scope":"global","decision":"deny"}]}')
elif command == "create":
    (guests / args[1]).mkdir()
elif command == "ls":
    print(json.dumps([
        {"name": path.name, "id": str(uuid.uuid5(uuid.NAMESPACE_OID, path.name)), "status": "stopped" if (path / "stopped").exists() else "running"}
        for path in guests.iterdir()
    ]))
elif command == "stop":
    (guests / args[0] / "stopped").touch()
elif command == "rm":
    shutil.rmtree(guests / args[1])
elif command == "cp":
    def translate(value):
        name, separator, path = value.partition(":")
        if not separator:
            return value
        assert path.startswith("/tmp/harborist-")
        return str(guests / name / Path(path).name)
    shutil.copyfile(*map(translate, args))
elif command == "exec":
    cwd = args[:3] == ["-i", "--workdir", "/home/agent/workspace/repository"]
    if cwd:
        args = args[3:]
    if args[:2] == ["-i", "--"]:
        args = args[2:]
    elif args[0] == "--":
        args = args[1:]
    name, *args = args
    guest = guests / name
    if args[0] == "dd":
        destination = args[1].removeprefix("of=")
        assert destination in ["/tmp/harborist-source.bundle", "/tmp/harborist-schema.json"]
        with (guest / Path(destination).name).open("wb") as stream:
            shutil.copyfileobj(sys.stdin.buffer, stream)
        sys.exit(0)
    def guest_arg(value):
        if value == "/home/agent/workspace/repository" or value.startswith("/tmp/harborist-"):
            return str(guest / Path(value).name)
        return value
    if cwd:
        assert args[:2] == ["timeout", "--kill-after=2s"]
        args = args[3:]
    env = {**os.environ, "IN_FIXTURE_GUEST": "1"}
    result = subprocess.run(
        list(map(guest_arg, args)),
        cwd=guest / "repository" if cwd else guest,
        env=env,
        check=False,
    )
    sys.exit(result.returncode)
else:
    raise AssertionError(command)
"""


@contextmanager
def host_connection(root: Path, env: dict[str, str]):
    helper = root / "helper"
    helper.mkdir()
    token = helper / "token"
    token.write_text("offline-helper-fixture-token".ljust(32, "0"))
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    binary = ROOT / "target/release/harborist-verify"
    with subprocess.Popen([binary, "sandbox-host", helper, str(port), "--sbx", root / "sbx"], env=env) as process:
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    assert process.poll() is None and time.monotonic() < deadline
                    time.sleep(0.025)
            yield {**env, "HARBORIST_SANDBOX_HOST": "127.0.0.1",
                   "HARBORIST_SANDBOX_PORT": str(port), "HARBORIST_SANDBOX_TOKEN_FILE": str(token)}
        finally:
            process.terminate()


def exercise(root: Path, check: str, expected: str, *, mutation: bool = False, hosted: bool = False) -> None:
    repo, base, _ = fixture(root, [check])
    canonical = Path("/opt/harborist/src/harborist")
    (repo / "harborist.settings.yaml").write_text(
        "version: 1\n"
        f"playbook: {{name: bounded-repository-change, version: '1', path: {canonical}/playbooks/bounded-repository-change.md}}\n"
        f"skills: [{{name: engineering, version: '2', path: {canonical}/skills/engineering.md}}]\n"
        "agent_profile: {name: local-codex, version: '1', provider: codex, model: fixture, arguments: []}\n"
        "sandbox_policy: {kind: docker-sandboxes}\n"
    )
    for name, content in [
        ("sbx", FAKE_SBX),
        ("codex", FAKE_CODEX.replace('args = sys.argv[1:]', 'assert os.environ["IN_FIXTURE_GUEST"] == "1"\nargs = sys.argv[1:]')),
    ]:
        executable = root / name
        executable.write_text(content)
        executable.chmod(0o755)
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    guests = root / "guests"
    guests.mkdir()
    history = root / "sbx-history"
    invocations = root / "invocations"
    output = root / "run"
    env = {
        **os.environ,
        "PATH": f"{root}:{os.environ['PATH']}",
        "INVOCATIONS": str(invocations),
        "FIXTURE_GUESTS": str(guests),
        "SBX_HISTORY": str(history),
    }
    connection = host_connection(root, env) if hosted else nullcontext(env)
    with connection as runtime_env:
        result = subprocess.run([
            ROOT / "target/release/harborist-verify", "run", repo, base, intent, output,
        ], env=runtime_env, capture_output=True, text=True, check=False)
    evidence = json.loads((output / "evidence.json").read_text())
    assert evidence["outcome"] == expected, (evidence, result.stderr)
    assert (result.returncode == 0) == (expected == "VERIFIED")
    candidate = evidence["candidate"]
    assert git(repo, "show", f"{candidate}:message.txt") == "hello from candidate"
    calls = [json.loads(line) for line in history.read_text().splitlines()]
    names = [call[2] for call in calls if call[0] == "create"]
    stages = ["design", "plan", "build", "test"]
    if expected == "VERIFIED":
        stages.append("review")
    assert [name.split("-")[1] for name in names] == stages
    assert len(set(names)) == len(stages)
    if mutation:
        [retained] = guests.iterdir()
        assert retained.name == names[-1] and (retained / "stopped").is_file()
        test = json.loads((output / "test/evidence.json").read_text())
        assert test["checks"][0]["returncode"] == 0 and not test["passed"]
        assert "changed the workspace" in test["workspace_error"]
    else:
        assert not list(guests.iterdir())
    assert invocations.read_text().splitlines() == [stage for stage in stages if stage != "test"]
    assert any(call[0] == "exec" and "/bin/sh" in call and call[-1] == check for call in calls)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory), 'test "$IN_FIXTURE_GUEST" = 1 && test -f message.txt', "VERIFIED")
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory), 'test "$IN_FIXTURE_GUEST" = 1 && false', "TEST_FAILED")
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory), "touch changed-by-test", "TEST_FAILED", mutation=True)
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory), 'test "$IN_FIXTURE_GUEST" = 1 && test -f message.txt', "VERIFIED", hosted=True)
    print("Rust authenticated host-helper workflow fixture passed.")
    print("Rust Docker Sandbox workflow fixture passed.")
