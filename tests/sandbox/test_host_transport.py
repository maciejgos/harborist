import http.client
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

import pytest

from shipyard.execution.process import ProcessCapture
from shipyard.sandbox.host_runtime import HostRuntime
from shipyard.sandbox.host_transport import Request, create_server, request_host


@contextmanager
def listener(tmp_path: Path) -> Generator[int]:
    def run(
        args: tuple[str, ...], *, timeout: float, limit: int, input_bytes: bytes
    ) -> ProcessCapture:
        assert args == ("version",)
        return ProcessCapture(0, False, b"v0.54.0", b"", False, False)

    with create_server(HostRuntime(tmp_path, run), b"test-token", port=0) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join()


def test_only_authenticated_bounded_requests_reach_sbx(tmp_path: Path) -> None:
    with listener(tmp_path) as port:
        request = Request(args=("version",), timeout=5, limit=1024)
        with pytest.raises(ValueError):
            request_host("127.0.0.1", port, b"wrong-token", request)
        assert (
            request_host("127.0.0.1", port, b"test-token", request).stdout == b"v0.54.0"
        )


def test_incomplete_body_does_not_reach_sbx(tmp_path: Path) -> None:
    with listener(tmp_path) as port:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request(
            "POST",
            "/v1/sandbox",
            b'{"args":',
            {"Content-Length": "100", "Authorization": "Bearer test-token"},
        )
        connection.close()
        request = Request(args=("version",), timeout=5, limit=1024)
        assert (
            request_host("127.0.0.1", port, b"test-token", request).stdout == b"v0.54.0"
        )


def test_disconnect_interrupts_running_adapter(tmp_path: Path) -> None:
    from threading import Event
    from time import sleep

    from shipyard.execution.cancellation import check_cancellation

    entered = Event()
    interrupted = Event()

    def run(
        args: tuple[str, ...], *, timeout: float, limit: int, input_bytes: bytes
    ) -> ProcessCapture:
        entered.set()
        try:
            for _ in range(100):
                check_cancellation()
                sleep(0.01)
        except KeyboardInterrupt:
            interrupted.set()
            raise
        return ProcessCapture(1, False, b"", b"", False, False)

    with create_server(HostRuntime(tmp_path, run), b"test-token", port=0) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
            connection.request(
                "POST",
                "/v1/sandbox",
                Request(args=("version",), timeout=2, limit=1024).model_dump_json(),
                {"Authorization": "Bearer test-token"},
            )
            assert entered.wait(1)
            connection.close()
            assert interrupted.wait(1)
        finally:
            server.shutdown()
            thread.join()
