"""Time both complete foreground paths with the same deterministic Codex fixture."""

import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from compare import ROOT, fixture, git
from foreground_test import FAKE_CODEX


def benchmark(root: Path, trials: int) -> None:
    repo, base, _ = fixture(root, [
        'test "$(cat message.txt)" = "hello from candidate"',
        "git diff --check HEAD^ HEAD",
        "wc -c < message.txt",
    ])
    intent = root / "issue.md"
    intent.write_text("Write the requested message.")
    codex = root / "codex"
    codex.write_text(FAKE_CODEX)
    codex.chmod(0o755)
    canonical = Path("/opt/harborist/src/harborist")
    settings = root / "settings.yaml"
    settings.write_text(
        "version: 1\n"
        f"playbook: {{name: bounded-repository-change, version: '1', path: {canonical}/playbooks/bounded-repository-change.md}}\n"
        f"skills: [{{name: engineering, version: '2', path: {canonical}/skills/engineering.md}}]\n"
        "agent_profile: {name: local-codex, version: '1', provider: codex, model: fixture, arguments: []}\n"
        "sandbox_policy: trusted-local\n"
    )
    samples: dict[str, list[float]] = {"Python": [], "Rust": []}
    baseline: tuple | None = None
    for index in range(trials + 2):
        order = tuple(samples) if index % 2 == 0 else tuple(reversed(samples))
        for language in order:
            trial = root / f"{language}-{index}"
            trial.mkdir()
            invocations = trial / "invocations"
            if language == "Python":
                command = [
                    sys.executable, "-m", "harborist", "run", f"file:{intent}",
                    "--foreground", "--json", "--repo", str(repo), "--ref", base,
                    "--settings", str(settings), "--runs-dir", str(trial / "runs"),
                    "--workspace", str(trial / "workspace"),
                ]
            else:
                command = [
                    str(ROOT / "target/release/harborist-verify"),
                    "run", str(repo), base, str(intent), str(trial / "run"),
                ]
            started = time.perf_counter_ns()
            result = subprocess.run(
                command,
                env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
                     "INVOCATIONS": str(invocations)},
                capture_output=True, text=True, check=False,
            )
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            assert result.returncode == 0, (language, result.stdout, result.stderr)
            summary = json.loads(result.stdout)
            if language == "Python":
                package = json.loads(Path(summary["evidence"]).read_text())
                outcome = package["run"]["outcome"]
                sha = package["candidate"]["candidate_sha"]
                checks = package["test"]["collection"]["checks"]
            else:
                outcome = summary["outcome"]
                sha = summary["candidate"]
                checks = json.loads((trial / "run/test/evidence.json").read_text())["checks"]
            assert outcome == "VERIFIED"
            assert invocations.read_text().splitlines() == ["design", "plan", "build", "review"]
            captured = tuple(
                (check["id"], check["returncode"],
                 Path(check["stdout_path"]).read_bytes(), Path(check["stderr_path"]).read_bytes())
                for check in checks
            )
            observed = (git(repo, "rev-parse", f"{sha}^{{tree}}"), captured)
            if baseline is None:
                baseline = observed
            assert observed == baseline
            if index >= 2:
                samples[language].append(elapsed)
    for language, timings in samples.items():
        p95 = statistics.quantiles(timings, n=100, method="inclusive")[94]
        print(f"{language} foreground: n={trials}, median={statistics.median(timings):.2f} ms, p95={p95:.2f} ms")
    print(f"Foreground median speedup: {statistics.median(samples['Python']) / statistics.median(samples['Rust']):.2f}x")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        benchmark(Path(directory), int(sys.argv[1]) if len(sys.argv) > 1 else 20)
