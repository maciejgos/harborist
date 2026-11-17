"""Resolve a saved target Workspace for an explicit ticket submission."""

from pathlib import Path
from uuid import UUID

from pydantic import UUID4, BaseModel, ConfigDict, Field

from shipyard.control.queue import Submission
from shipyard.control.saved_workspaces import WorkspaceStore
from shipyard.control.workspace import CaptureRequest, capture_submission
from shipyard.github.issues import parse_github_selector


class TicketListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    repository: str = Field(min_length=1, max_length=256)


class TicketQueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: UUID4
    source: str = Field(min_length=1, max_length=320)
    workspace_id: UUID


class _TicketCapture(CaptureRequest):
    workspace_id: UUID


def capture_ticket_submission(
    request: TicketQueueRequest,
    workspaces: WorkspaceStore,
    root: Path,
    *,
    receipts: Path,
) -> Submission:
    source = f"github:{request.source.removeprefix('github:')}"
    parse_github_selector(source)
    receipt = receipts / f"{request.request_id}.json"
    if receipt.exists():
        try:
            capture = _TicketCapture.model_validate_json(receipt.read_bytes())
        except ValueError as error:
            raise ValueError(
                "This request ID does not identify a ticket submission"
            ) from error
        if capture.workspace_id != request.workspace_id or capture.source != source:
            raise ValueError("This request ID was already used with different inputs")
    else:
        workspace = workspaces.get(request.workspace_id)
        capture = _TicketCapture(
            request_id=request.request_id,
            source=source,
            workspace_id=workspace.id,
            repository=workspace.repository,
            settings=workspace.settings,
            ref=workspace.ref,
            timeout=workspace.timeout,
            verification_reserve=workspace.verification_reserve,
        )
    return capture_submission(capture, root, receipts=receipts)
