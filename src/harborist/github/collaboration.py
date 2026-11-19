"""Bound and validate GitHub collaboration evidence."""

from collections.abc import Sequence

from pydantic import BaseModel, Field, TypeAdapter

from harborist.domain.revision import GitCommitSha
from harborist.github.cli import api


class User(BaseModel):
    login: str


class RemoteFeedback(BaseModel):
    id: int
    user: User | None
    body: str | None


class Feedback(BaseModel):
    key: str
    author: str
    body: str


class Check(BaseModel):
    name: str = Field(max_length=1024)
    status: str
    conclusion: str | None
    details_url: str | None


class CheckPage(BaseModel):
    total_count: int
    check_runs: tuple[Check, ...] = Field(max_length=50)


class Status(BaseModel):
    state: str
    context: str = Field(max_length=1024)
    target_url: str | None


class StatusPage(BaseModel):
    state: str
    total_count: int
    statuses: tuple[Status, ...] = Field(max_length=50)


def collect_feedback(repository: str, pull: int) -> tuple[Feedback, ...]:
    feedback: list[Feedback] = []
    for kind, endpoint in (
        ("review", f"pulls/{pull}/reviews"),
        ("inline", f"pulls/{pull}/comments"),
        ("comment", f"issues/{pull}/comments"),
    ):
        records = TypeAdapter(list[RemoteFeedback]).validate_python(
            api(f"repos/{repository}/{endpoint}?per_page=50")
        )
        feedback.extend(
            Feedback(
                key=f"{kind}:{record.id}",
                author=record.user.login if record.user else "unknown",
                body=record.body[:4000],
            )
            for record in records[:50]
            if record.body
            and record.body.strip()
            and not record.body.startswith("<!-- harborist-publication:")
        )
    return tuple(feedback)


def collect_ci(repository: str, head: GitCommitSha) -> tuple[CheckPage, StatusPage]:
    return (
        CheckPage.model_validate(
            api(f"repos/{repository}/commits/{head}/check-runs?per_page=50")
        ),
        StatusPage.model_validate(
            api(f"repos/{repository}/commits/{head}/status?per_page=50")
        ),
    )


def select_feedback(records: tuple[Feedback, ...], keys: Sequence[str]) -> str:
    by_key = {item.key: item for item in records}
    entries: list[str] = []
    for key in dict.fromkeys(keys):
        record = by_key.get(key)
        if record is None:
            raise ValueError(f"Unknown GitHub feedback ID {key}")
        entries.append(f"[{key}] {record.author}\n{record.body}")
    return "\n\n".join(entries)
