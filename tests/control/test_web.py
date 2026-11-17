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
    service = ControlService(queue, agent=FakeAgent(), history_root=tmp_path / "runs")
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
        origin = f"http://127.0.0.1:{server.server_port}"
        headers = {"Content-Type": "application/json", "X-Shipyard-Workspace": "1"}
        for value in ("https://other.example", "null"):
            connection.request(
                "POST", "/api/workspace/runs", "{}", {**headers, "Origin": value}
            )
            response = connection.getresponse()
            assert response.status == 403
            response.read()
        connection.request(
            "POST", "/api/workspace/runs", "{}", {**headers, "Origin": origin}
        )
        response = connection.getresponse()
        assert response.status == 400
        assert "error" in json.loads(response.read())
        for action in ("list", "queue"):
            route = f"/api/tickets/{action}"
            connection.request(
                "POST", route, "{}", {**headers, "Origin": "https://other.example"}
            )
            response = connection.getresponse()
            assert response.status == 403
            response.read()
            connection.request("POST", route, "{}", {**headers, "Origin": origin})
            response = connection.getresponse()
            assert response.status == 400
            assert "error" in json.loads(response.read())
        connection.close()
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()


def test_workspace_deep_link_serves_packaged_react_assets(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from shipyard.control.client import ControlClient

    app = WebApplication(ControlClient(tmp_path))
    for route in (f"/runs/{frozen_contract.run_id}", "/tickets"):
        status, _, html = app.respond("GET", route)
        assert status == 200
        assert b'id="root"' in html
        assert b'src="/app.js"' in html
    for route in ("/app.js", "/style.css"):
        status, _, content = app.respond("GET", route)
        assert status == 200 and content
    assert app.respond("GET", "/runs/invalid")[0] == 404


def test_attempt_evidence_is_read_through_the_selected_attempt(
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
    service = ControlService(queue, agent=FakeAgent(), history_root=tmp_path / "runs")
    service.worker.execute_next()
    prefix = f"/runs/{contract.run_id}/attempts"
    assert service.dispatch("GET", prefix, b"") == {"attempts": [0]}
    view = service.dispatch("GET", prefix + "/0", b"")
    assert view["attempt_number"] == 0
    assert view["candidate_sha"]
    assert service.dispatch("GET", prefix + "/0/artifacts/report.md", b"")["content"]
    with pytest.raises(ValueError, match="Unknown Attempt"):
        service.dispatch("GET", prefix + "/1", b"")


def test_browser_capture_retry_reuses_the_same_run(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from uuid import uuid4

    _, repo, _ = capture(tmp_path, frozen_contract)
    root = repo.checkout_root()
    request = tmp_path / "request.md"
    request.write_text("# Browser request\n")
    settings = Path("shipyard.settings.yaml").resolve()
    service = ControlService(
        QueueStore(tmp_path / "control"),
        agent=FakeAgent(),
        history_root=tmp_path / "web-runs",
    )
    payload = {
        "request_id": str(uuid4()),
        "source": f"file:{request}",
        "repository": str(root),
        "settings": str(settings),
    }
    body = json.dumps(payload).encode()
    first = service.dispatch("POST", "/workspace/runs", body)
    second = service.dispatch("POST", "/workspace/runs", body)
    assert first == second == {"run_id": payload["request_id"]}
    assert len(service.queue.list()) == 1
    with pytest.raises(ValueError, match="different inputs"):
        service.dispatch(
            "POST", "/workspace/runs", json.dumps({**payload, "ref": "other"}).encode()
        )


def test_browser_publication_uses_verified_application_operation(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shipyard.application import publication
    from shipyard.application.publication import Branch, PullRequest

    store, repo, contract = capture(tmp_path, frozen_contract)
    queue = QueueStore(tmp_path / "control")
    root = store.directory(contract.run_id).parent
    queue.submit(
        Submission(
            run_id=contract.run_id, repository=repo.checkout_root(), runs_root=root
        )
    )
    service = ControlService(queue, agent=FakeAgent(), history_root=root)
    service.worker.execute_next()
    verification = store.load_state(contract.run_id).verification
    assert verification is not None
    sha = verification.candidate.candidate_sha

    def publish(run_id: object, **options: object) -> PullRequest:
        assert run_id == contract.run_id
        assert options["approve"] == sha
        assert options["expected_attempt"] == verification.attempt.attempt_id
        assert options["runs_dir"] == root
        return PullRequest(
            number=1,
            html_url="https://github.com/example/project/pull/1",
            state="open",
            head=Branch(ref="shipyard", sha=sha),
            base=Branch(ref="main", sha=sha),
            body=None,
        )

    monkeypatch.setattr(publication, "publish_run", publish)
    path = f"/workspace/runs/{contract.run_id}/publish"
    response = service.dispatch(
        "POST",
        path,
        json.dumps(
            {
                "approve": sha,
                "expected_attempt": str(verification.attempt.attempt_id),
                "destination": "example/project",
                "base": "main",
            }
        ).encode(),
    )
    assert response["run_id"] == str(contract.run_id)
    assert response["pull"]


def test_browser_accepts_pasted_issue_and_home_paths() -> None:
    from shipyard.control.workspace import normalize_path, normalize_source

    assert (
        normalize_path(Path("~/Code/shipyard"), "Repository path")
        == Path.home() / "Code/shipyard"
    )
    assert (
        normalize_source("https://github.com/example/repo/issues/6?foo=bar")
        == "github:example/repo#6"
    )
    assert normalize_source("~/request.md") == f"file:{Path.home() / 'request.md'}"
    with pytest.raises(ValueError, match="Source"):
        normalize_source("https://example.com/example/repo/issues/6")


def test_saved_workspace_validates_and_reloads_checkout(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from uuid import uuid4

    from shipyard.control.saved_workspaces import WorkspaceSettings, WorkspaceStore

    _, repo, _ = capture(tmp_path, frozen_contract)
    workspace = WorkspaceSettings(
        id=uuid4(),
        name="Shipyard",
        repository=repo.checkout_root(),
        settings=Path("shipyard.settings.yaml").resolve(),
    )
    root = tmp_path / "workspaces"
    saved = WorkspaceStore(root).save(workspace)
    assert WorkspaceStore(root).list() == [saved]
    assert saved.repository == repo.checkout_root()
    with pytest.raises(ValueError):
        WorkspaceStore(root).save(workspace.model_copy(update={"ref": "unknown-ref"}))
    assert WorkspaceStore(root).list() == [saved]


def test_github_integration_distinguishes_login_and_repository_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    from shipyard.control import integrations

    def run(args: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args, 0 if args[1] == "auth" else 1)

    monkeypatch.setattr(integrations.subprocess, "run", run)
    result = integrations.check_github("example/repository")
    assert result["status"] == "repository_unavailable"
    assert integrations.check_github(None)["status"] == "connected"
