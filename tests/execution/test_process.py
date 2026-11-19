"""Bounded capture must not wait for detached descendants holding a pipe."""

import os
import signal
import sys
import time
from pathlib import Path

from harborist.execution.process import capture_process


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


def test_cancel_stops_running_process_group(tmp_path: Path) -> None:
    import pytest

    from harborist.execution.cancellation import cancellation_check

    marker = tmp_path / "started"
    token = cancellation_check.set(marker.exists)
    started = time.monotonic()
    try:
        with pytest.raises(KeyboardInterrupt):
            capture_process(
                [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(10)",
                ],
                cwd=tmp_path,
                timeout=10,
                limit=100,
            )
    finally:
        cancellation_check.reset(token)
    assert marker.exists()
    assert time.monotonic() - started < 5
