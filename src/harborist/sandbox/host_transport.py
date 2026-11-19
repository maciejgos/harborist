"""Authenticated, bounded transport between the worker and its local sbx host."""

import hmac
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from select import select
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from harborist.execution.cancellation import cancellation_check
from harborist.execution.process import ProcessCapture
from harborist.sandbox.host_runtime import (
    MAX_OUTPUT,
    MAX_SECONDS,
    MAX_TRANSFER,
    HostRuntime,
)

ROUTE = "/v1/sandbox"
MAX_REQUEST = (MAX_TRANSFER + 2) // 3 * 4 + 128 * 1024


class Request(BaseModel):
    model_config = ConfigDict(
        extra="forbid", ser_json_bytes="base64", val_json_bytes="base64"
    )

    args: Annotated[tuple[str, ...], Field(min_length=1, max_length=1024)]
    timeout: Annotated[float, Field(gt=0, le=MAX_SECONDS)]
    limit: Annotated[int, Field(gt=0, le=MAX_OUTPUT)]
    input_bytes: Annotated[bytes, Field(max_length=MAX_TRANSFER)] = b""


class Response(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )

    returncode: int
    timed_out: bool
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool

    def capture(self) -> ProcessCapture:
        return ProcessCapture(
            self.returncode,
            self.timed_out,
            self.stdout,
            self.stderr,
            self.stdout_truncated,
            self.stderr_truncated,
        )


def response_limit(output_limit: int) -> int:
    return 8 * ((output_limit + 2) // 3) + 1024


def request_host(host: str, port: int, token: bytes, request: Request) -> Response:
    connection = HTTPConnection(host, port, timeout=request.timeout + 10)
    try:
        connection.request(
            "POST",
            ROUTE,
            request.model_dump_json().encode(),
            {
                "Authorization": "Bearer " + token.decode("ascii"),
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        limit = response_limit(request.limit)
        if response.status != 200:
            raise ValueError("Host sandbox helper rejected the operation")
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Host sandbox response exceeded its limit")
        result = Response.model_validate_json(raw)
        if max(len(result.stdout), len(result.stderr)) > request.limit:
            raise ValueError("Host sandbox output exceeded its limit")
        return result
    finally:
        connection.close()


def create_server(
    runtime: HostRuntime, token: bytes, *, port: int
) -> ThreadingHTTPServer:
    authorization = b"Bearer " + token

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            self.request.settimeout(10)
            super().setup()

        def log_message(self, format: str, *args: object) -> None:
            pass

        def disconnected(self) -> bool:
            try:
                # One request per connection. Once the body has arrived, any
                # socket readability means EOF or unexpected client traffic.
                return bool(select([self.request], [], [], 0)[0])
            except OSError:
                return True

        def reply(self, status: int, body: bytes = b"") -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass

        def do_POST(self) -> None:
            supplied = self.headers.get("Authorization", "").encode("latin-1")
            if self.path != ROUTE or not hmac.compare_digest(supplied, authorization):
                self.reply(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST or self.headers.get(
                    "Transfer-Encoding"
                ):
                    raise ValueError("Invalid request framing")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request")
                request = Request.model_validate_json(raw)
                cancel = cancellation_check.set(self.disconnected)
                try:
                    result = runtime.execute(
                        request.args,
                        timeout=request.timeout,
                        limit=request.limit,
                        input_bytes=request.input_bytes,
                    )
                finally:
                    cancellation_check.reset(cancel)
                self.reply(
                    200, Response.model_validate(result).model_dump_json().encode()
                )
            except OSError, ValueError:
                self.reply(400)
            except KeyboardInterrupt:
                # capture_process stops its child when the worker disconnects.
                return

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
