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
from shipyard.intake.github import ticket_url


def test_gh_capture_is_explicit_and_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "title": "Fix café",
        "url": "https://github.com/acme/source/issues/42",
        "body": "Keep\r\nbody\n",
        "labels": [{"name": "z", "id": "label-id", "color": "fff"}, {"name": "a"}],
    }
    calls: list[list[str]] = []

    def gh(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(args, 0, json.dumps(response).encode())

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", gh)
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
            "title,body,labels,url",
        ]
    ]
    assert intent.source_ref == "github:acme/source#42"
    assert intent.source_url == response["url"]
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

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", unexpected)
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

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", gh)
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

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", gh)
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


def test_listing_rejects_a_url_for_a_different_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shipyard.github.issues import list_tickets

    def gh(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert args[args.index("--repo") + 1] == "acme/source"
        assert args[args.index("--state") + 1] == "open"
        assert args[args.index("--limit") + 1] == "100"
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(
            args,
            0,
            b'[{"number":42,"title":"Summary","labels":[],"url":"https://github.com/other/source/issues/42"}]',
        )

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", gh)
    with pytest.raises(GitHubIntakeError, match="invalid issue list") as caught:
        list_tickets("acme/source")
    assert "other/source" not in str(caught.value)


def test_capture_keeps_selector_and_canonical_url_after_repository_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_url = "https://github.com/acme/renamed/issues/42"

    def gh(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert args[args.index("--repo") + 1] == "acme/old"
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps(
                {
                    "title": "Intake title",
                    "body": "Intake body",
                    "labels": [{"name": "bug"}],
                    "url": canonical_url,
                }
            ).encode(),
        )

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", gh)
    intent = read_github_intent(run_id=uuid4(), source="github:acme/old#42")
    assert intent.source_ref == "github:acme/old#42"
    assert intent.markdown == '# Intake title\n\nLabels: ["bug"]\n\nIntake body'
    assert intent.source_url == canonical_url
    assert ticket_url(intent) == canonical_url


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com.example.org/acme/source/issues/42",
        "https://user@github.com/acme/source/issues/42",
        "https://github.com:443/acme/source/issues/42",
        "https://github.com/acme/source/issues/43",
        "https://github.com/acme/source/issues/42?x=1",
        "https://github.com/acme/source/issues/42#comment",
        "https://github.com/acme/../issues/42",
        "https://github.com/acme/sourcé/issues/42",
    ],
)
def test_capture_and_provenance_reject_invalid_issue_urls(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from shipyard.domain import IntentSnapshot

    source = "github:acme/source#42"
    raw = json.dumps({"title": "Issue", "body": "", "labels": [], "url": url}).encode()

    def gh(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args, 0, raw)

    monkeypatch.setattr("shipyard.github.issues.subprocess.run", gh)
    with pytest.raises(GitHubIntakeError, match="invalid response"):
        read_github_intent(run_id=uuid4(), source=source)
    saved = IntentSnapshot.create(
        run_id=uuid4(), source_ref=source, source_url=url, markdown="Issue"
    )
    assert ticket_url(saved) is None
