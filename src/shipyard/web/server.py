"""Loopback static UI and allowlisted GET proxy; no execution authority."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from shipyard.control.client import ControlClient


class WebApplication:
    def __init__(self, client: ControlClient) -> None:
        self.client = client

    def respond(self, method: str, path: str) -> tuple[int, str, bytes]:
        if method != "GET":
            return 405, "text/plain", b"Read-only monitor"
        route = urlsplit(path).path
        static = {
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "text/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        if route in static:
            name, mime = static[route]
            return (
                200,
                mime,
                files("shipyard.web").joinpath("assets", name).read_bytes(),
            )
        if route.startswith("/api/"):
            api = route.removeprefix("/api")
            parts = api.strip("/").split("/")
            allowed = api in ("/health", "/runs")
            if len(parts) in (2, 4) and parts[0] == "runs":
                try:
                    UUID(parts[1])
                except ValueError:
                    return 404, "text/plain", b"Unknown Run"
                allowed = len(parts) == 2 or (
                    parts[2] == "artifacts"
                    and parts[3] in ("report.md", "evidence.json")
                )
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


def create_server(*, control_dir: Path, port: int) -> ThreadingHTTPServer:
    app = WebApplication(ControlClient(control_dir))

    class Handler(BaseHTTPRequestHandler):
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
            # Reject DNS-rebinding Host values; the adapter never binds publicly.
            host = self.headers.get("Host", "")
            if host not in (
                f"127.0.0.1:{listener.server_port}",
                f"localhost:{listener.server_port}",
            ):
                status, mime, body = 403, "text/plain", b"Loopback host required"
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

    listener = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return listener
