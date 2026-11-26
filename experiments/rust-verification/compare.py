"""Exercise both implementations in the same Linux container."""

import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMANDS = {
    "Python": [sys.executable, str(ROOT / "python_reference.py")],
    "Rust": [str(ROOT / "target/release/harborist-verify")],
}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", repo, *args], text=True).strip()


def fixture(
    root: Path, commands: list[str], invalid_config: str | None = None
) -> tuple[Path, str, str]:
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Harborist benchmark")
    git(repo, "config", "user.email", "benchmark@example.invalid")
    checks = [{"id": f"check-{index}", "command": cmd}
              for index, cmd in enumerate(commands)]
    config = json.dumps({"version": 1, "checks": checks})
    (repo / "harborist.yaml").write_text(
        config if invalid_config is None else invalid_config
    )
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Freeze checks")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "message.txt").write_text("hello from candidate\n")
    (repo / "harborist.yaml").write_text("checks altered by candidate\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Add candidate message")
    return repo, base, git(repo, "rev-parse", "HEAD")


def run(root: Path, language: str, fixture_args: tuple[Path, str, str]):
    workspace = root / "checkout"
    logs = root / "logs"
    started = time.perf_counter_ns()
    result = subprocess.check_output([
        *COMMANDS[language], *map(str, fixture_args), str(workspace), str(logs),
    ])
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    assert not workspace.exists()
    evidence = json.loads(result)
    captured = {}
    for check in evidence["checks"]:
        for stream in ("stdout", "stderr"):
            field = f"{stream}_path"
            path = Path(check[field])
            assert path.parent == logs
            captured[path.name] = path.read_bytes()
            check[field] = path.name
    assert len(captured) == 2 * len(evidence["checks"])
    for path in logs.iterdir():
        path.unlink()
    logs.rmdir()
    return (evidence, captured), elapsed


def test_parity(root: Path) -> None:
    args = fixture(root, [
        'test "$(cat message.txt)" = "hello from candidate"',
        "printf error >&2; exit 7",
        "head -c 65537 /dev/zero",
        "sleep 10",
        "printf still-ran",
    ])
    reference, _ = run(root, "Python", args)
    port, _ = run(root, "Rust", args)
    assert port == reference, (port[0], reference[0])
    evidence, logs = port
    assert not evidence["passed"]
    assert [item["returncode"] for item in evidence["checks"]] == [0, 7, 0, -9, 0]
    assert evidence["checks"][2]["stdout_truncated"]
    assert evidence["checks"][3]["timed_out"]
    assert logs["0004.stdout.log"] == b"still-ran"
    print("Parity passed for frozen configuration, failure, truncation, timeout, and continuation.")


def test_invalid_config(root: Path) -> None:
    root.mkdir()
    args = fixture(root, [], invalid_config="version: 1\nchecks: [{id: 42, command: true}]\n")
    workspace, logs = root / "checkout", root / "logs"
    failures = {}
    for language, command in COMMANDS.items():
        result = subprocess.run(
            [*command, *map(str, args), str(workspace), str(logs)],
            capture_output=True,
            check=False,
        )
        failures[language] = result.returncode
        if logs.exists():
            for path in logs.iterdir():
                path.unlink()
            logs.rmdir()
    assert all(failures.values()), failures
    assert not workspace.exists()
    print("Both implementations rejected non-string check fields.")


def benchmark(root: Path, trials: int) -> None:
    args = fixture(root, [
        'test "$(cat message.txt)" = "hello from candidate"',
        "git diff --check HEAD^ HEAD",
        "wc -c < message.txt",
    ])
    reference, _ = run(root, "Python", args)
    assert reference[0]["passed"]
    samples: dict[str, list[float]] = {language: [] for language in COMMANDS}
    for iteration in range(trials + 3):
        order = tuple(COMMANDS) if iteration % 2 == 0 else tuple(reversed(COMMANDS))
        for language in order:
            result, elapsed = run(root, language, args)
            assert result == reference
            if iteration >= 3:
                samples[language].append(elapsed)
    for language, timings in samples.items():
        p95 = statistics.quantiles(timings, n=100, method="inclusive")[94]
        print(f"{language}: n={trials}, median={statistics.median(timings):.2f} ms,"
              f" p95={p95:.2f} ms")
    print(f"Median speedup: {statistics.median(samples['Python']) / statistics.median(samples['Rust']):.2f}x")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        if len(sys.argv) > 1:
            benchmark(root, int(sys.argv[1]))
        else:
            test_parity(root)
            test_invalid_config(root / "invalid")
