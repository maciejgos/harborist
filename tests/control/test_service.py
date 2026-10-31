import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import UUID

import pytest

from shipyard.agents.base import AgentRequest, AgentResponse
from shipyard.control.client import ControlClient
from shipyard.control.queue import QueueStore
from shipyard.control.service import ControlService, ServiceOwnership
from shipyard.domain import RunContract
from tests.application.test_run_execution import FakeAgent


def test_exclusive_owner_and_os_release() -> None:
    with TemporaryDirectory(prefix="sy-", dir="/tmp") as directory:
        root = Path(directory)
        with (
            ServiceOwnership(root),
            pytest.raises(ValueError, match="already running"),
            ServiceOwnership(root),
        ):
            pass
        with ServiceOwnership(root):
            pass


def test_local_health_stop_and_private_socket() -> None:
    with TemporaryDirectory(prefix="sy-", dir="/tmp") as directory:
        root = Path(directory)
        service = ControlService(QueueStore(root), agent=FakeAgent())
        thread = Thread(target=service.serve)
        thread.start()
        assert service.ready.wait(5)
        try:
            client = ControlClient(root)
            assert client.request("GET", "/health")["version"] == 1
            assert (root / "service.sock").stat().st_mode & 0o777 == 0o600
            with pytest.raises(ValueError, match="Unknown"):
                client.request("GET", "/unknown")
            client.request("POST", "/stop")
        finally:
            service.stop()
            thread.join(5)
        assert not thread.is_alive()
        assert not (root / "service.sock").exists()


def test_invalid_json_request_has_explicit_error() -> None:
    with TemporaryDirectory(prefix="sy-", dir="/tmp") as directory:
        root = Path(directory)
        service = ControlService(QueueStore(root), agent=FakeAgent())
        thread = Thread(target=service.serve)
        thread.start()
        assert service.ready.wait(5)
        try:
            with socket.socket(socket.AF_UNIX) as connection:
                connection.connect(str(root / "service.sock"))
                connection.sendall(b"POST /runs HTTP/1.0\r\nContent-Length: 1\r\n\r\n{")
                response = b""
                while block := connection.recv(4096):
                    response += block
            assert b"400 Bad Request" in response
            assert "error" in json.loads(response.split(b"\r\n\r\n")[1])
        finally:
            service.stop()
            thread.join(5)


def test_stop_drains_active_run_and_preserves_pending_claims(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from threading import Event

    from shipyard.control.queue import DeliveryState, Submission
    from shipyard.domain import IntentSnapshot, RunContract
    from shipyard.persistence import FileRunStore
    from tests.application.test_run_execution import capture

    entered, release = Event(), Event()

    class BlockingAgent(FakeAgent):
        def execute(self, request: AgentRequest) -> AgentResponse:
            entered.set()
            assert release.wait(5)
            return super().execute(request)

    store, repository, contract = capture(tmp_path, frozen_contract)
    second_id = UUID("00000000-0000-4000-8000-000000000002")
    second = RunContract.model_validate(
        {
            **contract.model_dump(),
            "run_id": second_id,
            "intent": IntentSnapshot.create(
                run_id=second_id, source_ref="file:/other.md", markdown="Other"
            ),
        }
    )
    store.save(second)
    with TemporaryDirectory(prefix="sy-", dir="/tmp") as directory:
        queue = QueueStore(Path(directory))
        for run_id in (contract.run_id, second_id):
            queue.submit(
                Submission(
                    run_id=run_id,
                    repository=repository.checkout_root(),
                    runs_root=store.directory(run_id).parent,
                )
            )
        service = ControlService(queue, agent=BlockingAgent())
        thread = Thread(target=service.serve)
        thread.start()
        try:
            assert service.ready.wait(5)
            assert entered.wait(5)
            client = ControlClient(queue.root)
            client.request("POST", "/stop")
            assert thread.is_alive()
            with pytest.raises(ValueError, match="stopping"):
                client.request(
                    "POST",
                    "/runs",
                    queue.get(second_id).submission.model_dump(mode="json"),
                )
        finally:
            release.set()
            service.stop()
            thread.join(10)
        assert not thread.is_alive()
        assert queue.get(contract.run_id).state == DeliveryState.FINISHED
        assert queue.get(second_id).state == DeliveryState.QUEUED
        assert (
            FileRunStore(root=store.directory(second_id).parent)
            .load_state(second_id)
            .lifecycle
            == "CREATED"
        )
