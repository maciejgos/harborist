"""Run the loopback helper as the local Docker Sandboxes operator."""

import argparse
import fcntl
import os
from pathlib import Path

from harborist.execution.process import ProcessCapture, capture_process
from harborist.sandbox.host_runtime import HostRuntime
from harborist.sandbox.host_transport import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("port", type=int)
    parser.add_argument("--sbx", default="sbx")
    options = parser.parse_args()
    directory: Path = options.directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.umask(0o077)
    directory.chmod(0o700)
    executable = str(options.sbx)
    token = (directory / "token").read_bytes().strip()
    if len(token) < 32:
        parser.error("Sandbox helper token is missing or invalid")

    def run(
        args: tuple[str, ...], *, timeout: float, limit: int, input_bytes: bytes
    ) -> ProcessCapture:
        return capture_process(
            [executable, "--no-input", *args],
            cwd=directory,
            timeout=timeout,
            limit=limit,
            input_bytes=input_bytes,
            env={
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "SSH_AUTH_SOCK",
                    "GH_TOKEN",
                    "GITHUB_TOKEN",
                    "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY",
                }
            },
        )

    with (directory / "helper.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with create_server(
            HostRuntime(directory, run), token, port=options.port
        ) as server:
            server.serve_forever()


if __name__ == "__main__":
    main()
