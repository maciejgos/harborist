"""Small HTTP/JSON client over the local owner's Unix socket."""

import http.client
import json
import socket
from pathlib import Path
from typing import cast


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, *, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.path = path
        self.timeout = timeout

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))


class ControlClient:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        timeout: float = 10,
    ) -> dict[str, object]:
        connection = UnixConnection(self.root / "service.sock", timeout=timeout)
        try:
            connection.request(
                method,
                path,
                body=json.dumps(payload) if payload is not None else None,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            value: object = json.loads(response.read(4 * 1024 * 1024))
            if not isinstance(value, dict):
                raise ValueError("Invalid service response")  # noqa: TRY004 - protocol validation
            result = cast(dict[str, object], value)
            if response.status >= 400:
                raise ValueError(str(result.get("error", "Service request failed")))
            return result
        except (OSError, http.client.HTTPException) as error:
            raise ValueError(
                f"Cannot reach Shipyard service in {self.root}; run "
                f"shipyard service start --control-dir {self.root}. "
                "Captured Runs are retained."
            ) from error
        finally:
            connection.close()
