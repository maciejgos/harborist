import json
from pathlib import Path

import pytest

from shipyard.control.queue import Progress, QueueStore, Submission
from shipyard.control.service import ControlService
from shipyard.domain import RunContract
from shipyard.web.server import WebApplication
from tests.application.test_run_execution import FakeAgent, capture


def test_stage_updates_survive_reload_without_implying_missing_stages(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    queue = QueueStore(tmp_path / "control")
    queue.submit(
        Submission(
            run_id=contract.run_id,
            repository=repo.checkout_root(),
            runs_root=store.directory(contract.run_id).parent,
        )
    )
    queue.claim()
    queue.update_progress(contract.run_id, Progress(stage="design", state="completed"))
    queue.update_progress(contract.run_id, Progress(stage="plan", state="started"))
    record = QueueStore(queue.root).get(contract.run_id)
    assert record.stages["design"].state == "completed"
    assert record.stages["plan"].state == "started"
    assert "build" not in record.stages


def test_artifact_api_only_reads_named_terminal_artifacts(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    store, repo, contract = capture(tmp_path, frozen_contract)
    queue = QueueStore(tmp_path / "control")
    queue.submit(
        Submission(
            run_id=contract.run_id,
            repository=repo.checkout_root(),
            runs_root=store.directory(contract.run_id).parent,
        )
    )
    service = ControlService(queue, agent=FakeAgent())
    prefix = f"/runs/{contract.run_id}/artifacts/"
    with pytest.raises(ValueError):
        service.dispatch("GET", prefix + "report.md", b"")
    service.worker.execute_next()
    result = service.dispatch("GET", prefix + "report.md", b"")
    assert (
        result["content"]
        == (store.directory(contract.run_id) / "report.md").read_text()
    )
    view = service.dispatch("GET", f"/runs/{contract.run_id}", b"")
    assert view["title"]
    verification = store.load_state(contract.run_id).verification
    assert verification is not None
    assert view["candidate_sha"] == verification.candidate.candidate_sha
    for name in ("../../contract.json", "contract.json", "workspace/.git"):
        with pytest.raises(ValueError):
            service.dispatch("GET", prefix + name, b"")
    report = store.directory(contract.run_id) / "report.md"
    report.unlink()
    report.symlink_to(tmp_path / "secret")
    with pytest.raises(ValueError):
        service.dispatch("GET", prefix + "report.md", b"")


def test_web_adapter_is_read_only_and_has_no_filesystem_routes(tmp_path: Path) -> None:
    from shipyard.control.client import ControlClient

    app = WebApplication(ControlClient(tmp_path))
    status, mime, body = app.respond("GET", "/")
    assert status == 200 and "text/html" in mime
    assert b"Shipyard" in body
    for method, route in (
        ("POST", "/api/runs"),
        ("POST", "/api/stop"),
        ("GET", "/../../etc/passwd"),
        ("GET", "/api/stop"),
    ):
        status, _, _ = app.respond(method, route)
        assert status in (404, 405)
    status, _, body = app.respond("GET", "/api/runs")
    assert status == 503
    assert "error" in json.loads(body)


def test_loopback_http_rejects_foreign_hosts_and_mutations(tmp_path: Path) -> None:
    import http.client
    from threading import Thread

    from shipyard.web.server import create_server

    server = create_server(control_dir=tmp_path, port=0)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Security-Policy")
        assert b"Shipyard" in response.read()
        connection.request("GET", "/", headers={"Host": "other.example"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.request("POST", "/api/runs")
        response = connection.getresponse()
        assert response.status == 405
        response.read()
        connection.close()
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()
