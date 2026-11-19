"""Sequential trusted-local shell checks with complete collection and file logs."""

import math
import time
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from harborist.domain import VerificationConfig
from harborist.execution.process import ProcessCapture, capture_process


class CheckExecutor(Protocol):
    def __call__(
        self, command: list[str], *, cwd: Path, timeout: float, limit: int
    ) -> ProcessCapture: ...


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    command: str
    returncode: int | None
    timed_out: bool
    error: str | None
    stdout_path: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False
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
    total_timeout_seconds: float | None = None,
    max_log_bytes: int = 65536,
    executor: CheckExecutor = capture_process,
) -> CheckCollection:
    """Run all checks, even after failure; log I/O errors abort evidence capture."""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("Check timeout must be finite and positive")
    if total_timeout_seconds is not None and (
        not math.isfinite(total_timeout_seconds) or total_timeout_seconds <= 0
    ):
        raise ValueError("Total timeout must be finite and positive")
    if max_log_bytes < 0:
        raise ValueError("Log limit must be nonnegative")
    deadline = (
        None
        if total_timeout_seconds is None
        else time.monotonic() + total_timeout_seconds
    )
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
        stdout_truncated = stderr_truncated = False
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            allowance = (
                timeout_seconds
                if deadline is None
                else min(timeout_seconds, deadline - time.monotonic())
            )
            if allowance <= 0:
                timed_out = True
                error = "Shared TEST deadline exhausted before invocation"
            else:
                try:
                    capture = executor(
                        ["/bin/sh", "-c", check.command],
                        cwd=workspace,
                        timeout=allowance,
                        limit=max_log_bytes,
                    )
                    returncode = capture.returncode
                    timed_out = capture.timed_out
                    stdout.write(capture.stdout)
                    stderr.write(capture.stderr)
                    stdout_truncated = capture.stdout_truncated
                    stderr_truncated = capture.stderr_truncated
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
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )
        )
    return CheckCollection(checks=tuple(results))
