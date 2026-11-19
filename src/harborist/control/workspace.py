"""Typed commands for the local browser workspace."""

import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field

from harborist.application.capture import capture_run
from harborist.application.context import (
    ExecutionContext,
    load_context,
    resolve_context,
)
from harborist.control.queue import Submission
from harborist.control.read_model import RunView
from harborist.domain.continuation import ContinuationRequest
from harborist.github.issues import parse_github_selector
from harborist.persistence import FileRunStore
from harborist.persistence.application import ensure_record_directory, write_new_record


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID4
    source: str = Field(min_length=1, max_length=4096)
    repository: Path
    settings: Path | None = None
    ref: str = Field(default="HEAD", min_length=1, max_length=256)
    timeout: int = Field(default=1800, gt=0, strict=True)
    verification_reserve: int = Field(default=300, gt=0, strict=True)


class SupersedeRequest(CaptureRequest):
    reason: str = Field(min_length=1, max_length=1000)


def normalize_path(path: Path, label: str) -> Path:
    if str(path) == "~" or str(path).startswith("~/"):
        path = path.expanduser()
    if not path.is_absolute():
        raise ValueError(f"{label}: enter an absolute path or a path starting with ~/")
    return path


def normalize_source(source: str) -> str:
    if source.startswith("https://"):
        parsed = urlsplit(source)
        match = re.fullmatch(r"/([^/]+/[^/]+)/issues/([1-9][0-9]*)/?", parsed.path)
        if parsed.netloc.lower() != "github.com" or not match:
            raise ValueError(
                "Source: paste a github.com issue URL or enter a Markdown path"
            )
        source = f"github:{match[1]}#{match[2]}"
    if source.startswith("github:"):
        parse_github_selector(source)
        return source
    path = normalize_path(Path(source.removeprefix("file:")), "Source")
    return f"file:{path}"


def capture_submission(
    request: CaptureRequest, root: Path, *, receipts: Path
) -> Submission:
    source = normalize_source(request.source)
    repository_path = normalize_path(request.repository, "Repository path")
    settings = (
        normalize_path(request.settings, "Settings path") if request.settings else None
    )
    if request.timeout <= request.verification_reserve:
        raise ValueError("Total time must exceed the verification reserve")
    ensure_record_directory(receipts)
    receipt = receipts / f"{request.request_id}.json"
    store = FileRunStore(root=root)
    directory = store.original_directory(request.request_id)
    if receipt.exists():
        if type(request).model_validate_json(receipt.read_bytes()) != request:
            raise ValueError("This request ID was already used with different inputs")
    elif directory.exists():
        raise ValueError("This request ID already belongs to a saved Run")
    else:
        write_new_record(receipt, request)
    context_path = directory / "execution-context.json"
    if directory.exists():
        store.load(request.request_id)
        if not context_path.exists():
            from harborist.git import GitRepository

            ExecutionContext(
                version=1,
                run_id=request.request_id,
                repository=GitRepository(path=repository_path).checkout_root(),
                runs_root=root,
            ).save()
        context = load_context(path=context_path, run_id=request.request_id)
        if context.runs_root != root:
            raise ValueError("Captured Run belongs to a different Runs root")
        repository = context.repository
    else:
        _, repository, _ = capture_run(
            source=source,
            settings=settings,
            repo=repository_path,
            ref=request.ref,
            runs_dir=root,
            timeout=request.timeout,
            verification_reserve=request.verification_reserve,
            run_id=request.request_id,
        )
    return Submission(run_id=request.request_id, repository=repository, runs_root=root)


def continuation_submission(
    record: RunView, request: ContinuationRequest
) -> Submission:
    run_id = record.submission.run_id
    root = record.submission.runs_root
    repository = (
        record.submission.repository
        if isinstance(record.submission, Submission)
        else resolve_context(run_id=run_id, runs_dir=root)[0]
    )
    return Submission(
        run_id=run_id, repository=repository, runs_root=root, continuation=request
    )


def run_id_response(run_id: UUID) -> dict[str, object]:
    return {"run_id": str(run_id)}
