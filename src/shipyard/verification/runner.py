"""Sequential trusted-local shell checks with complete collection and file logs."""

import math
import os
import signal
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from shipyard.domain import VerificationConfig


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    command: str
    returncode: int | None
    timed_out: bool
    error: str | None
    stdout_path: str
    stderr_path: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.error is None


class CheckCollection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


def run_checks(
    *,
    config: VerificationConfig,
    workspace: Path,
    logs_dir: Path,
    timeout_seconds: float,
) -> CheckCollection:
    """Run all checks, even after failure; log I/O errors abort evidence capture."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Check timeout must be finite and positive")
    workspace = workspace.resolve(strict=True)
    logs_dir = logs_dir.resolve()
    logs_dir.mkdir()
    results: list[CheckResult] = []
    for index, check in enumerate(config.checks):
        stdout_path = logs_dir / f"{index:04d}.stdout.log"
        stderr_path = logs_dir / f"{index:04d}.stderr.log"
        returncode = None
        timed_out = False
        error = None
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            try:
                process = subprocess.Popen(
                    ["/bin/sh", "-c", check.command],
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                )
                try:
                    returncode = process.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    returncode = process.wait()
            except OSError as cause:
                error = str(cause)
        results.append(
            CheckResult(
                id=check.id,
                command=check.command,
                returncode=returncode,
                timed_out=timed_out,
                error=error,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
            )
        )
    return CheckCollection(checks=tuple(results))
