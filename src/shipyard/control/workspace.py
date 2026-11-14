"""Typed commands for the local browser workspace."""

from pathlib import Path
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field

from shipyard.application.capture import capture_run
from shipyard.application.context import ExecutionContext, load_context, resolve_context
from shipyard.control.queue import Submission
from shipyard.control.read_model import RunView
from shipyard.domain.continuation import ContinuationRequest
from shipyard.persistence import FileRunStore
from shipyard.persistence.application import ensure_record_directory, write_new_record


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


def capture_submission(
    request: CaptureRequest, root: Path, *, receipts: Path
) -> Submission:
    source = request.source
    if not request.repository.is_absolute() or (
        request.settings is not None and not request.settings.is_absolute()
    ):
        raise ValueError("Use absolute paths for the repository and settings")
    if source.startswith("file:") and not Path(source[5:]).is_absolute():
        raise ValueError("Use an absolute path for the Markdown source")
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
            from shipyard.git import GitRepository

            ExecutionContext(
                version=1,
                run_id=request.request_id,
                repository=GitRepository(path=request.repository).checkout_root(),
                runs_root=root,
            ).save()
        context = load_context(path=context_path, run_id=request.request_id)
        if context.runs_root != root:
            raise ValueError("Captured Run belongs to a different Runs root")
        repository = context.repository
    else:
        _, repository, _ = capture_run(
            source=source,
            settings=request.settings,
            repo=request.repository,
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
