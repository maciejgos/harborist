from pathlib import Path
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from harborist.cli import app
from harborist.control.client import ControlClient


def test_ticket_commands_request_fresh_listings_and_queue_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = str(uuid4())
    calls: list[tuple[str, str, dict[str, object] | None, float]] = []

    def request(
        self: ControlClient,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        timeout: float = 10,
    ) -> dict[str, object]:
        assert self.root == tmp_path.resolve()
        calls.append((method, path, payload, timeout))
        if path == "/tickets/queue":
            assert payload is not None
            assert payload["workspace_id"] == workspace_id
            assert payload["source"] == "acme/source#42"
            assert UUID(str(payload["request_id"])).version == 4
            return {"run_id": payload["request_id"]}
        assert payload == {"repository": "acme/source"}
        if len(calls) == 1:
            return {
                "issues": [
                    {
                        "identity": "acme/source#42",
                        "title": "Repair login",
                        "labels": ["bug", "auth"],
                        "url": "https://github.com/acme/source/issues/42",
                    }
                ]
            }
        if len(calls) == 2:
            return {"issues": []}
        raise ValueError("Run gh auth login and check access.")

    monkeypatch.setattr(ControlClient, "request", request)

    def invoke(*arguments: str):
        return CliRunner().invoke(
            app, ["tickets", *arguments, "--control-dir", str(tmp_path)]
        )

    listed = invoke("list", "acme/source")
    assert listed.exit_code == 0, listed.output
    assert all(
        text in listed.stdout
        for text in ("acme/source#42", "Repair login", "bug", "auth")
    )
    empty = invoke("refresh", "acme/source")
    assert empty.exit_code == 0
    assert "No open issues" in empty.stdout
    failed = invoke("refresh", "acme/source")
    assert failed.exit_code == 1
    assert "gh auth login" in failed.stderr
    assert not failed.stdout
    queued = invoke("queue", "acme/source#42", "--workspace", workspace_id)
    assert queued.exit_code == 0, queued.output
    request_payload = calls[-1][2]
    assert request_payload is not None
    assert str(request_payload["request_id"]) in queued.stdout
    assert [item[1] for item in calls] == ["/tickets/list"] * 3 + ["/tickets/queue"]
    assert all(method == "POST" and timeout > 30 for method, _, _, timeout in calls)
