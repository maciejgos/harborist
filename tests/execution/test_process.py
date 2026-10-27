"""Bounded capture must not wait for detached descendants holding a pipe."""

import os
import signal
import sys
import time
from pathlib import Path

from shipyard.execution.process import capture_process


def test_detached_descendant_cannot_keep_capture_open(tmp_path: Path) -> None:
    started = time.monotonic()
    result = capture_process(
        [
            sys.executable,
            "-c",
            "import subprocess; p = subprocess.Popen(['sleep', '3'], start_new_session=True); print(p.pid, flush=True)",
        ],
        cwd=tmp_path,
        timeout=0.2,
        limit=100,
    )
    try:
        assert time.monotonic() - started < 2
        assert result.returncode == 0
    finally:
        try:
            os.kill(int(result.stdout), signal.SIGKILL)
        except ProcessLookupError:
            pass
