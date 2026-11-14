"""Drain subprocess pipes continuously, retaining only a bounded prefix."""

import math
import os
import selectors
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from shipyard.execution.cancellation import check_cancellation


@dataclass(frozen=True)
class ProcessCapture:
    returncode: int
    timed_out: bool
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool


def capture_process(
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
    limit: int,
    input_bytes: bytes = b"",
) -> ProcessCapture:
    if limit < 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(
            "Log limit must be nonnegative and timeout finite and positive"
        )
    check_cancellation()
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]
    deadline = time.monotonic() + timeout

    def terminate(process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    with tempfile.TemporaryFile() as stdin:
        stdin.write(input_bytes)
        stdin.seek(0)
        with (
            subprocess.Popen(
                command,
                cwd=cwd,
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            ) as process,
            selectors.DefaultSelector() as selector,
        ):
            assert process.stdout is not None and process.stderr is not None
            for index, pipe in enumerate((process.stdout, process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, index)
            timed_out = False
            try:
                while True:
                    check_cancellation()
                    exited = process.poll() is not None
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 and not exited:
                        timed_out = True
                        terminate(process)
                        process.wait()
                        exited = True
                    if exited:
                        terminate(process)
                    ready = selector.select(
                        0 if exited else min(0.05, max(0, remaining))
                    )
                    for key, _ in ready:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        index = cast(int, key.data)
                        available = max(0, limit - len(buffers[index]))
                        buffers[index].extend(chunk[:available])
                        truncated[index] |= len(chunk) > available
                    # Detached descendants may retain pipes after the executor exits.
                    # Drain available bytes, then close instead of waiting for their EOF.
                    if exited and (not ready or remaining <= 0):
                        for key in selector.get_map().values():
                            truncated[key.data] = True
                        break
            finally:
                terminate(process)
                process.wait()
                process.stdout.close()
                process.stderr.close()
            return ProcessCapture(
                process.returncode,
                timed_out,
                bytes(buffers[0]),
                bytes(buffers[1]),
                truncated[0],
                truncated[1],
            )
