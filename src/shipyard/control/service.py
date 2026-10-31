"""Single local service owner, HTTP admission and a serial execution loop."""

import fcntl
import json
import os
import stat
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import UnixStreamServer
from threading import Event, RLock, Thread
from typing import BinaryIO, Self
from uuid import UUID

from shipyard.agents.base import NativeAgent
from shipyard.control.queue import QueueStore, Submission
from shipyard.control.read_model import read_record
from shipyard.control.worker import Worker

MAX_REQUEST = 64 * 1024


class ServiceOwnership:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.file: BinaryIO | None = None

    def __enter__(self) -> Self:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_uid != os.getuid():
            raise ValueError("Control directory must be owned by the current user")
        self.root.chmod(0o700)
        self.file = (self.root / "service.lock").open("ab")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.file.close()
            self.file = None
            raise ValueError(
                "Shipyard service already running for this directory"
            ) from error
        return self

    def __exit__(self, *_: object) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None


class ControlService:
    def __init__(self, queue: QueueStore, *, agent: NativeAgent) -> None:
        self.queue = queue
        self.worker = Worker(queue, agent=agent)
        self.stopping = Event()
        self.ready = Event()
        self.gate = RLock()

    def stop(self) -> None:
        with self.gate:
            self.stopping.set()

    def dispatch(self, method: str, path: str, body: bytes) -> dict[str, object]:
        if method == "GET" and path == "/health":
            return {"version": 1, "stopping": self.stopping.is_set()}
        if method == "POST" and path == "/stop":
            self.stop()
            return {"stopping": True}
        if method == "POST" and path == "/runs":
            submission = Submission.model_validate_json(body)
            with self.gate:
                if self.stopping.is_set():
                    raise ValueError("Service is stopping; submission was not accepted")
                return self.queue.submit(submission).model_dump(mode="json")
        if method == "GET" and path == "/runs":
            return {
                "runs": [
                    read_record(item).model_dump(mode="json")
                    for item in self.queue.list()
                ]
            }
        if method == "GET" and path.startswith("/runs/"):
            return read_record(
                self.queue.get(UUID(path.removeprefix("/runs/")))
            ).model_dump(mode="json")
        raise ValueError("Unknown service route or method")

    def serve(self) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                self.request.settimeout(5)
                super().setup()

            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                self.respond()

            def do_POST(self) -> None:
                self.respond()

            def respond(self) -> None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if (
                        self.headers.get("Transfer-Encoding")
                        or not 0 <= length <= MAX_REQUEST
                    ):
                        raise ValueError(
                            "Request body too large or unsupported encoding"
                        )
                    body = self.rfile.read(length)
                    if len(body) != length:
                        raise ValueError("Incomplete request body")
                    result = service.dispatch(self.command, self.path, body)
                    status = 200
                except (ValueError, OSError) as error:
                    result = {"error": str(error)[:4096]}
                    status = 400
                encoded = json.dumps(result).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                except BrokenPipeError, ConnectionResetError:
                    # Durable acceptance is independent of the client's lifetime.
                    pass

        socket_path = self.queue.root / "service.sock"
        with ServiceOwnership(self.queue.root):
            if socket_path.exists() or socket_path.is_symlink():
                if not stat.S_ISSOCK(socket_path.lstat().st_mode):
                    raise ValueError(
                        "Service socket path is obstructed by a non-socket"
                    )
                socket_path.unlink()
            self.queue.interrupt_claims()
            with UnixStreamServer(str(socket_path), Handler) as server:
                socket_path.chmod(0o600)
                thread = Thread(
                    target=server.serve_forever, kwargs={"poll_interval": 0.1}
                )
                thread.start()
                self.ready.set()
                try:
                    while not self.stopping.is_set():
                        with self.gate:
                            record = (
                                None if self.stopping.is_set() else self.queue.claim()
                            )
                        if record is None:
                            self.stopping.wait(0.1)
                        else:
                            self.worker.execute(record)
                finally:
                    self.stopping.set()
                    server.shutdown()
                    thread.join()
                    socket_path.unlink(missing_ok=True)
