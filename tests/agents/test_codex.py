import sys
from pathlib import Path

import pytest

from harborist.agents.base import AgentExecutionError
from harborist.agents.codex import CodexAgent
from tests.agents.test_base import request


def fake(root: Path, body: str) -> Path:
    path = root / "fake-codex"
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o755)
    return path


def test_fresh_exec_uses_final_message_not_stdout(tmp_path: Path) -> None:
    executable = fake(
        tmp_path,
        """import json, pathlib, sys
args = sys.argv[1:]
assert args[0] == 'exec'
assert '--ephemeral' in args
assert args[args.index('--sandbox') + 1] == 'read-only'
assert 'resume' not in args and 'fork' not in args
prompt = sys.stdin.read()
assert 'Do the thing' in prompt and 'design' in prompt
schema = pathlib.Path(args[args.index('--output-schema') + 1])
assert json.loads(schema.read_text())['additionalProperties'] is False
pathlib.Path(args[args.index('--output-last-message') + 1]).write_text('FINAL')
print('not a stage result')
""",
    )
    req = request(tmp_path)
    agent = CodexAgent(executable=str(executable))
    assert agent.execute(req).output == "FINAL"
    assert agent.execute(req).output == "FINAL"


@pytest.mark.parametrize(
    "body",
    [
        "raise SystemExit(7)",
        "pass",
        "import time; time.sleep(10)",
    ],
)
def test_process_failures(tmp_path: Path, body: str) -> None:
    req = request(tmp_path)
    req = req.model_copy(update={"timeout_seconds": 1})
    with pytest.raises(AgentExecutionError):
        CodexAgent(executable=str(fake(tmp_path, body))).execute(req)


def test_profile_cannot_override_execution_controls(tmp_path: Path) -> None:
    req = request(tmp_path)
    profile = req.profile.model_copy(
        update={"arguments": ("--sandbox", "danger-full-access")}
    )
    req = req.model_copy(update={"profile": profile})
    with pytest.raises(AgentExecutionError, match="argument"):
        CodexAgent(executable="must-not-launch").execute(req)


def test_missing_executable_and_invalid_final_bytes(tmp_path: Path) -> None:
    req = request(tmp_path)
    with pytest.raises(AgentExecutionError):
        CodexAgent(executable=str(tmp_path / "missing")).execute(req)
    executable = fake(
        tmp_path,
        """import pathlib, sys
args = sys.argv[1:]
pathlib.Path(args[args.index('--output-last-message') + 1]).write_bytes(b'\\xff')
""",
    )
    with pytest.raises(AgentExecutionError):
        CodexAgent(executable=str(executable)).execute(req)


def test_supported_effort_is_passed_without_shell(tmp_path: Path) -> None:
    req = request(tmp_path)
    profile = req.profile.model_copy(
        update={"arguments": ("-c", 'model_reasoning_effort="high"')}
    )
    req = req.model_copy(update={"profile": profile})
    executable = fake(
        tmp_path,
        """import pathlib, sys
args = sys.argv[1:]
assert args[1:3] == ['-c', 'model_reasoning_effort="high"']
assert args[args.index('--model') + 1] == 'test'
pathlib.Path(args[args.index('--output-last-message') + 1]).write_text('{}')
""",
    )
    assert CodexAgent(executable=str(executable)).execute(req).returncode == 0
