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
        service = ControlService(
            QueueStore(root), agent=FakeAgent(), history_root=root / "runs"
        )
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
        service = ControlService(
            QueueStore(root), agent=FakeAgent(), history_root=root / "runs"
        )
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
        service = ControlService(
            queue, agent=BlockingAgent(), history_root=tmp_path / "runs"
        )
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


def test_ticket_is_recaptured_for_the_independent_workspace(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from uuid import uuid4

    from typer.testing import CliRunner

    from shipyard.cli import app
    from shipyard.control.saved_workspaces import WorkspaceSettings
    from shipyard.persistence import FileRunStore
    from tests.application.test_run_execution import capture
    from tests.git_helpers import git

    _, checkout, _ = capture(tmp_path, frozen_contract)
    repository = checkout.checkout_root()
    git(repository, "remote", "add", "origin", "https://github.com/other/target.git")
    queue = QueueStore(tmp_path / "control")
    root = tmp_path / "ticket-runs"
    service = ControlService(queue, agent=FakeAgent(), history_root=root)
    workspace = service.workspaces.save(
        WorkspaceSettings(
            id=uuid4(),
            name="Target",
            repository=repository,
            settings=Path("shipyard.settings.yaml").resolve(),
            timeout=900,
            verification_reserve=200,
        )
    )
    assert workspace.github_repository == "other/target"
    url = "https://github.com/acme/source/issues/42"
    commands: list[str] = []
    listed_title = "Listed title"

    original_run = subprocess.run

    def gh(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if args[0] != "gh":
            return original_run(args, **kwargs)  # type: ignore[arg-type]
        assert args[args.index("--repo") + 1] == "acme/source"
        commands.append(args[2])
        common = {"url": url, "labels": [{"name": "bug"}]}
        if args[2] == "list":
            data = [{**common, "title": listed_title, "number": 42}]
        elif args[3] == "42":
            data = {**common, "title": "Intake title", "body": "Authoritative body"}
        else:
            raise subprocess.CalledProcessError(1, args, stderr=b"private diagnostic")
        return subprocess.CompletedProcess(args, 0, json.dumps(data).encode())

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", gh)
    listing = b'{"repository":"acme/source"}'
    assert service.dispatch("POST", "/tickets/list", listing) == {
        "issues": [
            {
                "identity": "acme/source#42",
                "title": "Listed title",
                "url": url,
                "labels": ["bug"],
            }
        ]
    }
    assert queue.list() == []
    payload = {
        "request_id": str(uuid4()),
        "source": "acme/source#42",
        "workspace_id": str(workspace.id),
    }

    def submit(**changes: str) -> dict[str, object]:
        return service.dispatch(
            "POST", "/tickets/queue", json.dumps({**payload, **changes}).encode()
        )

    with pytest.raises(ValueError, match="Workspace was not found"):
        submit(workspace_id=str(uuid4()))
    with pytest.raises(ValueError, match="gh auth login") as caught:
        submit(request_id=str(uuid4()), source="acme/source#43")
    assert "private diagnostic" not in str(caught.value)
    assert queue.list() == []
    assert submit() == {"run_id": payload["request_id"]}
    service.workspaces.save(workspace.model_copy(update={"timeout": 1000}))
    assert submit() == {"run_id": payload["request_id"]}
    with pytest.raises(ValueError, match="different inputs"):
        submit(source="acme/source#43")
    assert len(queue.list()) == 1
    assert queue.list()[0].submission.repository == repository
    run_id = UUID(payload["request_id"])
    listed_title = "Later edit"
    assert "Later edit" in json.dumps(
        service.dispatch("POST", "/tickets/list", listing)
    )
    contract = FileRunStore(root=root).load(run_id)
    assert contract.execution.budget.total_seconds == 900
    assert contract.execution.budget.verification_reserve_seconds == 200
    assert (
        contract.intent.markdown
        == '# Intake title\n\nLabels: ["bug"]\n\nAuthoritative body'
    )
    detail = service.dispatch("GET", f"/runs/{run_id}", b"")
    assert detail["source_ref"] == "github:acme/source#42"
    assert detail["source_url"] == url
    result = CliRunner().invoke(app, ["inspect", str(run_id), "--runs-dir", str(root)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["intent"]["source_url"] == url
    assert commands == ["list", "view", "view", "list"]


def test_older_saved_contract_shows_its_ticket_without_recapture(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from typer.testing import CliRunner

    from shipyard.cli import app
    from shipyard.domain import IntentSnapshot
    from shipyard.persistence import FileRunStore

    root = tmp_path / "runs"
    run_id = frozen_contract.run_id
    contract = frozen_contract.model_copy(
        update={
            "intent": IntentSnapshot.create(
                run_id=run_id,
                source_ref="github:old/source#7",
                markdown="# Historical issue",
            ),
        }
    )
    store = FileRunStore(root=root)
    store.save(contract)
    saved = store.directory(run_id) / "contract.json"
    payload = json.loads(saved.read_bytes())
    assert "source_url" not in payload["intent"]
    service = ControlService(
        QueueStore(tmp_path / "control"), agent=FakeAgent(), history_root=root
    )
    detail = service.dispatch("GET", f"/runs/{run_id}", b"")
    assert detail["source_ref"] == "github:old/source#7"
    assert detail["source_url"] == "https://github.com/old/source/issues/7"

    result = CliRunner().invoke(app, ["inspect", str(run_id), "--runs-dir", str(root)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["intent"]["source_url"] == detail["source_url"]
    assert json.loads(saved.read_bytes()) == payload
