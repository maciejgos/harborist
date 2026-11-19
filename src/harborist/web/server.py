"""Loopback workspace with allowlisted requests to the local service."""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID

from harborist.control.client import ControlClient
from harborist.control.evidence_reads import ATTEMPTS
from harborist.control.integrations import CODEX_PROFILE_ROUTE, SANDBOX_POLICY_ROUTE
from harborist.control.service import MAX_REQUEST

COMMAND = re.compile(
    r"/workspaces|/integrations/(?:github|codex/check|sandbox/check)|/tickets/(?:list|queue)|/workspace/runs(?:/([0-9a-f-]{36})/(?:continue|cancel|supersede|publish|observe))?"
)


class WebApplication:
    def __init__(self, client: ControlClient) -> None:
        self.client = client

    def command(self, path: str, raw: bytes) -> tuple[int, str, bytes]:
        route = urlsplit(path).path.removeprefix("/api")
        try:
            payload: object = json.loads(raw)
            if not isinstance(payload, dict):
                raise TypeError("Expected a JSON object")
            body = self.client.request(
                "POST", route, cast(dict[str, object], payload), timeout=180
            )
        except (TypeError, ValueError) as error:
            return 400, "application/json", json.dumps({"error": str(error)}).encode()
        return 200, "application/json", json.dumps(body).encode()

    def respond(self, method: str, path: str) -> tuple[int, str, bytes]:
        if method != "GET":
            return 405, "text/plain", b"Method not allowed"
        route = urlsplit(path).path
        static = {
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        if route in ("/workspaces", "/integrations", "/tickets"):
            route = "/"
        if route.startswith("/runs/"):
            run_id = route.removeprefix("/runs/")
            try:
                UUID(run_id)
            except ValueError:
                return 404, "text/plain", b"Unknown Run"
            route = "/"
        if route in static:
            name, mime = static[route]
            return (
                200,
                mime,
                files("harborist.web").joinpath("assets", name).read_bytes(),
            )
        if route.startswith("/api/"):
            api = route.removeprefix("/api")
            parts = api.strip("/").split("/")
            allowed = api in ("/health", "/runs", "/workspaces") or bool(
                CODEX_PROFILE_ROUTE.fullmatch(api)
                or SANDBOX_POLICY_ROUTE.fullmatch(api)
            )
            if len(parts) in (2, 3, 4) and parts[0] == "runs":
                try:
                    UUID(parts[1])
                except ValueError:
                    return 404, "text/plain", b"Unknown Run"
                allowed = (
                    len(parts) == 2
                    or (len(parts) == 3 and parts[2] == "github")
                    or (
                        len(parts) == 4
                        and parts[2] == "artifacts"
                        and parts[3] in ("report.md", "evidence.json")
                    )
                )
            if attempt := ATTEMPTS.fullmatch(api):
                try:
                    UUID(attempt[1])
                except ValueError:
                    return 404, "text/plain", b"Unknown Run"
                allowed = True
            if not allowed:
                return 404, "text/plain", b"Unknown route"
            try:
                body = self.client.request("GET", api)
                return 200, "application/json", json.dumps(body).encode()
            except ValueError as error:
                return (
                    503,
                    "application/json",
                    json.dumps({"error": str(error)}).encode(),
                )
        return 404, "text/plain", b"Not found"


def create_server(
    *, control_dir: Path, port: int, container_listener: bool = False
) -> ThreadingHTTPServer:
    app = WebApplication(ControlClient(control_dir))

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            self.request.settimeout(8)
            super().setup()

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.respond()

        def do_POST(self) -> None:
            self.respond()

        def do_PUT(self) -> None:
            self.respond()

        def do_DELETE(self) -> None:
            self.respond()

        def respond(self) -> None:
            # Reject DNS-rebinding Host values even with container port publishing.
            host = self.headers.get("Host", "")
            route = urlsplit(self.path).path.removeprefix("/api")
            if host not in (
                f"127.0.0.1:{listener.server_port}",
                f"localhost:{listener.server_port}",
            ):
                status, mime, body = 403, "text/plain", b"Loopback host required"
            elif (
                self.command == "POST"
                and self.path.startswith("/api/")
                and (
                    COMMAND.fullmatch(route)
                    or CODEX_PROFILE_ROUTE.fullmatch(route)
                    or SANDBOX_POLICY_ROUTE.fullmatch(route)
                )
            ):
                status, mime, body = self.workspace_command(host)
            else:
                status, mime, body = app.respond(self.command, self.path)
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError, ConnectionResetError:
                pass

        def workspace_command(self, host: str) -> tuple[int, str, bytes]:
            if (
                self.headers.get("Origin") != f"http://{host}"
                or self.headers.get("X-Harborist-Workspace") != "1"
            ):
                return (
                    403,
                    "application/json",
                    b'{"error":"Same-origin workspace request required"}',
                )
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if (
                    self.headers.get("Transfer-Encoding")
                    or not 0 < length <= MAX_REQUEST
                    or self.headers.get_content_type() != "application/json"
                ):
                    raise ValueError("Expected a bounded JSON request body")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request body")
            except (OSError, ValueError) as error:
                return (
                    400,
                    "application/json",
                    json.dumps({"error": str(error)}).encode(),
                )
            return app.command(self.path, raw)

    bind_address = "0.0.0.0" if container_listener else "127.0.0.1"
    listener = ThreadingHTTPServer((bind_address, port), Handler)
    return listener
