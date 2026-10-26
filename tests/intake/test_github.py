"""GitHub intake captures one authoritative issue response via local gh."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from shipyard.intake import (
    GitHubIntakeError,
    IntakeSourceError,
    capture_intent,
    read_github_intent,
)


def test_gh_capture_is_explicit_and_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "title": "Fix café",
        "body": "Keep\r\nbody\n",
        "labels": [{"name": "z", "id": "label-id", "color": "fff"}, {"name": "a"}],
    }
    calls: list[list[str]] = []

    def gh(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        assert kwargs == {"check": True, "capture_output": True, "timeout": 30}
        return subprocess.CompletedProcess(args, 0, json.dumps(response).encode())

    monkeypatch.setattr("shipyard.intake.github.subprocess.run", gh)
    intent = read_github_intent(run_id=uuid4(), source="github:acme/source#42")
    assert calls == [
        [
            "gh",
            "issue",
            "view",
            "42",
            "--repo",
            "acme/source",
            "--json",
            "title,body,labels",
        ]
    ]
    assert intent.source_ref == "github:acme/source#42"
    assert intent.markdown == '# Fix café\n\nLabels: ["a", "z"]\n\nKeep\r\nbody\n'
    response["body"] = "Edited after capture"
    assert "Edited" not in intent.markdown


@pytest.mark.parametrize(
    "source",
    [
        "github:--help/repo#1",
        "github:a/b#0",
        "github:a/b#1/other",
        "https://github.com/a/b/issues/1",
    ],
)
def test_bad_selector_rejected_before_process(
    source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid selector must not launch gh")

    monkeypatch.setattr("shipyard.intake.github.subprocess.run", unexpected)
    with pytest.raises(GitHubIntakeError):
        read_github_intent(run_id=uuid4(), source=source)


@pytest.mark.parametrize(
    "output",
    [
        b"not json",
        b'{"title": "Issue", "body": null, "labels": []}',
        b'{"title": "Issue", "body": "", "labels": [1]}',
    ],
)
def test_invalid_response_is_wrapped(
    output: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gh(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(["gh"], 0, output)

    monkeypatch.setattr("shipyard.intake.github.subprocess.run", gh)
    with pytest.raises(GitHubIntakeError) as caught:
        read_github_intent(run_id=uuid4(), source="github:a/b#1")
    assert caught.value.__cause__ is not None


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("gh missing"),
        subprocess.CalledProcessError(1, ["gh"]),
        subprocess.TimeoutExpired(["gh"], 30),
    ],
)
def test_gh_failures_preserve_causes(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gh(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise error

    monkeypatch.setattr("shipyard.intake.github.subprocess.run", gh)
    with pytest.raises(GitHubIntakeError) as caught:
        read_github_intent(run_id=uuid4(), source="github:a/b#1")
    assert caught.value.__cause__ is error


def test_dispatch_preserves_markdown_without_imposing_metadata_schema(
    tmp_path: Path,
) -> None:
    source = tmp_path / "issue.md"
    source.write_bytes(b"---\r\nanything: accepted\r\n---\r\nRequest\r\n")
    intent = capture_intent(run_id=uuid4(), source=f"file:{source}")
    assert intent.markdown.encode() == source.read_bytes()
    with pytest.raises(IntakeSourceError):
        capture_intent(run_id=uuid4(), source="file:")
    with pytest.raises(IntakeSourceError):
        capture_intent(run_id=uuid4(), source="https://example.com/issue")
