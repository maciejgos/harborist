"""Drain subprocess pipes continuously, retaining only a bounded prefix."""

import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import BinaryIO


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
    if limit < 0:
        raise ValueError("Log limit must be nonnegative")
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]
    errors: list[Exception] = []

    def drain(pipe: BinaryIO, index: int) -> None:
        try:
            with pipe:
                while chunk := pipe.read(65536):
                    available = max(0, limit - len(buffers[index]))
                    buffers[index].extend(chunk[:available])
                    truncated[index] |= len(chunk) > available
        except OSError as error:
            errors.append(error)

    with tempfile.TemporaryFile() as stdin:
        stdin.write(input_bytes)
        stdin.seek(0)
        with subprocess.Popen(
            command,
            cwd=cwd,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            assert process.stdout is not None and process.stderr is not None
            threads = [
                Thread(target=drain, args=(pipe, index))
                for index, pipe in enumerate((process.stdout, process.stderr))
            ]
            for thread in threads:
                thread.start()
            timed_out = False
            try:
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
            finally:
                # Also close pipes inherited by background descendants on normal exit.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                for thread in threads:
                    thread.join()
            if errors:
                raise errors[0]
            return ProcessCapture(
                process.returncode,
                timed_out,
                bytes(buffers[0]),
                bytes(buffers[1]),
                truncated[0],
                truncated[1],
            )
