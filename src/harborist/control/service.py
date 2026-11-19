"""Single local service owner, HTTP admission and a serial execution loop."""

import fcntl
import json
import os
import re
import stat
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import UnixStreamServer
from threading import Event, RLock, Thread
from typing import BinaryIO, Self
from uuid import UUID

from pydantic import ValidationError

from harborist.agents.base import NativeAgent
from harborist.agents.codex import CodexAgent
from harborist.configuration.execution import (
    CodexProfileSetup,
    codex_profile_status,
    configure_codex_profile,
    configure_sandbox_policy,
    execution_settings_path,
    sandbox_policy_status,
)
from harborist.control.evidence_reads import ATTEMPTS, attempt_evidence
from harborist.control.github_delivery import github_command, read_delivery
from harborist.control.history import RunHistory
from harborist.control.integrations import (
    CODEX_PROFILE_ROUTE,
    SANDBOX_POLICY_ROUTE,
    GitHubCheck,
    SandboxPolicyEdit,
    check_github,
)
from harborist.control.queue import QueueRecord, QueueStore, Submission
from harborist.control.retirement import retire_run, supersede_run
from harborist.control.saved_workspaces import WorkspaceSettings, WorkspaceStore
from harborist.control.tickets import (
    TicketListRequest,
    TicketQueueRequest,
    capture_ticket_submission,
)
from harborist.control.worker import Worker
from harborist.control.workspace import (
    CaptureRequest,
    SupersedeRequest,
    capture_submission,
    continuation_submission,
    run_id_response,
)
from harborist.domain import RunLifecycle
from harborist.domain.continuation import ContinuationRequest
from harborist.domain.sandbox import SandboxPolicy
from harborist.github.issues import list_tickets
from harborist.paths import runs_root
from harborist.persistence import FileRunStore
from harborist.persistence.retirement import RetirementRequest
from harborist.sandbox.docker import DockerSandboxRuntime

MAX_REQUEST = 64 * 1024


class ServiceOwnership:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.file: BinaryIO | None = None

    def __enter__(self) -> Self:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_uid != os.getuid():
            raise ValueError("Control directory must be owned by the current user")
        self.root.chmod(0o700)
        self.file = (self.root / "service.lock").open("ab")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.file.close()
            self.file = None
            raise ValueError(
                "Harborist service already running for this directory"
            ) from error
        return self

    def __exit__(self, *_: object) -> None:
        if self.file is not None:
            self.file.close()
            self.file = None


class ControlService:
    def __init__(
        self, queue: QueueStore, *, agent: NativeAgent, history_root: Path | None = None
    ) -> None:
        self.history = RunHistory(
            queue, root=history_root if history_root is not None else runs_root()
        )
        self.queue = queue
        self.workspaces = WorkspaceStore(queue.root / "workspaces")
        self.codex = agent if isinstance(agent, CodexAgent) else None
        self.worker = Worker(queue, agent=agent)
        self.stopping = Event()
        self.ready = Event()
        self.gate = RLock()
        self.active: QueueRecord | None = None

    def stop(self) -> None:
        with self.gate:
            self.stopping.set()

    def dispatch(self, method: str, path: str, body: bytes) -> dict[str, object]:
        if method == "GET" and path == "/health":
            return {"version": 1, "stopping": self.stopping.is_set()}
        if method == "POST" and path == "/stop":
            self.stop()
            return {"stopping": True}
        if method == "POST" and path == "/integrations/github":
            request = GitHubCheck.model_validate_json(body)
            repository = None
            if request.workspace_id:
                workspace = self.workspaces.get(request.workspace_id)
                repository = workspace.github_repository
                if repository is None:
                    raise ValueError(
                        "Set a GitHub repository in this Workspace before checking access"
                    )
            return check_github(repository)
        if method == "POST" and path == "/integrations/codex/check":
            if self.codex is None:
                raise ValueError("The local service is not using the Codex adapter")
            return dict(self.codex.check_connection())
        if method == "POST" and path == "/integrations/sandbox/check":
            if body != b"{}":
                raise ValueError("Sandbox readiness expects an empty request")
            return DockerSandboxRuntime().check()
        if method in ("GET", "POST") and (
            match := SANDBOX_POLICY_ROUTE.fullmatch(path)
        ):
            workspace = self.workspaces.get(UUID(match[1]))
            settings = execution_settings_path(workspace.repository, workspace.settings)
            if method == "GET":
                return {
                    **sandbox_policy_status(settings),
                    "defaults": SandboxPolicy().model_dump(mode="json"),
                }
            try:
                policy = SandboxPolicyEdit.model_validate_json(body).policy
            except ValidationError as error:
                raise ValueError(
                    "Enter valid runtime resources and hostname rules; URLs, credentials, and unrestricted wildcards are not accepted."
                ) from error
            configure_sandbox_policy(settings, policy)
            return {"status": "saved"}
        if method in ("GET", "POST") and (
            profile := CODEX_PROFILE_ROUTE.fullmatch(path)
        ):
            workspace = self.workspaces.get(UUID(profile[1]))
            settings = execution_settings_path(workspace.repository, workspace.settings)
            if method == "GET":
                return codex_profile_status(settings)
            try:
                setup = CodexProfileSetup.model_validate_json(body)
            except ValidationError as error:
                raise ValueError(
                    "Enter a valid Codex model identifier and supported reasoning effort."
                ) from error
            configure_codex_profile(settings, setup)
            return {"status": "saved"}
        if method == "POST" and path == "/tickets/list":
            listing = TicketListRequest.model_validate_json(body)
            return {
                "issues": [
                    ticket.model_dump(mode="json")
                    for ticket in list_tickets(listing.repository)
                ]
            }
        if method == "POST" and path == "/tickets/queue":
            ticket = TicketQueueRequest.model_validate_json(body)
            submission = capture_ticket_submission(
                ticket,
                self.workspaces,
                self.history.root,
                receipts=self.queue.root / "workspace-requests",
            )
            self.dispatch("POST", "/runs", submission.model_dump_json().encode())
            return run_id_response(submission.run_id)
        if path == "/workspaces":
            if method == "GET":
                return {
                    "workspaces": [
                        item.model_dump(mode="json") for item in self.workspaces.list()
                    ]
                }
            if method == "POST":
                saved = self.workspaces.save(
                    WorkspaceSettings.model_validate_json(body)
                )
                return saved.model_dump(mode="json")
        if method == "POST" and path.startswith("/workspace/runs"):
            return self.workspace_command(path, body)
        disposition = re.fullmatch(r"/runs/([^/]+)/(cancel|supersede)", path)
        if method == "POST" and disposition:
            run_id = UUID(disposition[1])
            request = RetirementRequest.model_validate_json(body)
            with self.gate:
                root = self.run_root(run_id, request)
                if disposition[2] == "supersede":
                    if self.stopping.is_set():
                        raise ValueError(
                            "Service is stopping; replacement was not accepted"
                        )
                    result = supersede_run(
                        self.queue, root, run_id, request, self.active
                    )
                else:
                    if request.replacement is not None:
                        raise ValueError("Use the supersede route for a replacement")
                    result = retire_run(self.queue, root, run_id, request, self.active)
                return result.model_dump(mode="json")
        if method == "POST" and path == "/runs":
            submission = Submission.model_validate_json(body)
            with self.gate:
                if self.stopping.is_set():
                    raise ValueError("Service is stopping; submission was not accepted")
                return self.queue.submit(submission).model_dump(mode="json")
        if method == "GET" and path == "/runs":
            return {
                "runs": [item.model_dump(mode="json") for item in self.history.list()]
            }
        if method == "GET" and (
            delivery := re.fullmatch(r"/runs/([^/]+)/github", path)
        ):
            return read_delivery(self.history.get(UUID(delivery[1])))
        if method == "GET" and (attempt := ATTEMPTS.fullmatch(path)):
            return attempt_evidence(
                self.history.get(UUID(attempt[1])), attempt[2], attempt[3]
            )
        if method == "GET" and "/artifacts/" in path:
            parts = path.strip("/").split("/")
            if (
                len(parts) != 4
                or parts[0] != "runs"
                or parts[2] != "artifacts"
                or parts[3] not in ("report.md", "evidence.json")
            ):
                raise ValueError("Unknown artifact route")
            record = self.history.get(UUID(parts[1]))
            if record.run is None:
                raise ValueError(
                    "Run records are unavailable; cannot read terminal artifacts"
                )
            store = FileRunStore(root=record.submission.runs_root)
            state = store.load_state(record.submission.run_id)
            if state.lifecycle not in (
                RunLifecycle.COMPLETED,
                RunLifecycle.FAILED,
                RunLifecycle.CANCELLED,
            ):
                raise ValueError("Terminal artifact is not available yet")
            directory = store.directory(record.submission.run_id)
            artifact = directory / parts[3]
            if (
                directory.is_symlink()
                or artifact.is_symlink()
                or artifact.resolve().parent != directory.resolve()
            ):
                raise ValueError("Artifact must be a regular file inside its Run")
            with artifact.open("rb") as source:
                content = source.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError("Artifact exceeds the 2 MiB viewing limit")
            return {"name": parts[3], "content": content.decode("utf-8")}
        if method == "GET" and path.startswith("/runs/"):
            return self.history.get(UUID(path.removeprefix("/runs/"))).model_dump(
                mode="json"
            )
        raise ValueError("Unknown service route or method")

    def workspace_command(self, path: str, body: bytes) -> dict[str, object]:
        if path == "/workspace/runs":
            request = CaptureRequest.model_validate_json(body)
            submission = capture_submission(
                request,
                self.history.root,
                receipts=self.queue.root / "workspace-requests",
            )
            self.dispatch("POST", "/runs", submission.model_dump_json().encode())
            return run_id_response(submission.run_id)
        match = re.fullmatch(
            r"/workspace/runs/([^/]+)/(continue|cancel|supersede|publish|observe)", path
        )
        if match is None:
            raise ValueError("Unknown workspace command")
        run_id = UUID(match[1])
        record = self.history.get(run_id)
        root = record.submission.runs_root
        if match[2] in ("publish", "observe"):
            return github_command(record, match[2], body)
        if match[2] == "continue":
            continuation = ContinuationRequest.model_validate_json(body)
            submission = continuation_submission(record, continuation)
            self.dispatch("POST", "/runs", submission.model_dump_json().encode())
            return run_id_response(run_id)
        if match[2] == "cancel":
            request_data = RetirementRequest.model_validate_json(body)
            retirement = RetirementRequest(reason=request_data.reason, runs_root=root)
        else:
            replacement = SupersedeRequest.model_validate_json(body)
            submission = capture_submission(
                replacement,
                root,
                receipts=self.queue.root / "workspace-requests" / str(run_id),
            )
            retirement = RetirementRequest(
                reason=replacement.reason, runs_root=root, replacement=submission.run_id
            )
        self.dispatch(
            "POST", f"/runs/{run_id}/{match[2]}", retirement.model_dump_json().encode()
        )
        return run_id_response(retirement.replacement or run_id)

    def run_root(self, run_id: UUID, request: RetirementRequest) -> Path:
        record = next(
            (item for item in self.queue.list() if item.submission.run_id == run_id),
            None,
        )
        if record is not None:
            root = record.submission.runs_root
            if request.runs_root and request.runs_root.resolve() != root:
                raise ValueError("Runs root conflicts with the service delivery")
            return root
        return request.runs_root.resolve() if request.runs_root else self.history.root

    def serve(self) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                self.request.settimeout(5)
                super().setup()

            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                self.respond()

            def do_POST(self) -> None:
                self.respond()

            def respond(self) -> None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if (
                        self.headers.get("Transfer-Encoding")
                        or not 0 <= length <= MAX_REQUEST
                    ):
                        raise ValueError(
                            "Request body too large or unsupported encoding"
                        )
                    body = self.rfile.read(length)
                    if len(body) != length:
                        raise ValueError("Incomplete request body")
                    result = service.dispatch(self.command, self.path, body)
                    status = 200
                except (ValueError, OSError) as error:
                    result = {"error": str(error)[:4096]}
                    status = 400
                encoded = json.dumps(result).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                except BrokenPipeError, ConnectionResetError:
                    # Durable acceptance is independent of the client's lifetime.
                    pass

        socket_path = self.queue.root / "service.sock"
        with ServiceOwnership(self.queue.root):
            if socket_path.exists() or socket_path.is_symlink():
                if not stat.S_ISSOCK(socket_path.lstat().st_mode):
                    raise ValueError(
                        "Service socket path is obstructed by a non-socket"
                    )
                socket_path.unlink()
            self.queue.interrupt_claims()
            with UnixStreamServer(str(socket_path), Handler) as server:
                socket_path.chmod(0o600)
                thread = Thread(
                    target=server.serve_forever, kwargs={"poll_interval": 0.1}
                )
                thread.start()
                self.ready.set()
                try:
                    while not self.stopping.is_set():
                        with self.gate:
                            record = (
                                None if self.stopping.is_set() else self.queue.claim()
                            )
                            self.active = record
                        if record is None:
                            self.stopping.wait(0.1)
                        else:
                            try:
                                self.worker.execute(record)
                            finally:
                                with self.gate:
                                    self.active = None
                finally:
                    self.stopping.set()
                    server.shutdown()
                    thread.join()
                    socket_path.unlink(missing_ok=True)
