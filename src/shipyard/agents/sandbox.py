"""Fresh sandboxed Codex invocations using the existing NativeAgent contract."""

import json
from pathlib import Path

from shipyard.agents.base import (
    AgentExecutionError,
    AgentRequest,
    AgentResponse,
    AgentTimeoutError,
    output_schema,
)
from shipyard.agents.codex import format_prompt, validate_profile
from shipyard.domain.sandbox import SandboxPolicy
from shipyard.domain.stage_result import AgentStage
from shipyard.sandbox.docker import GUEST_REPOSITORY, DockerSandboxRuntime


class SandboxCodexAgent:
    def __init__(
        self,
        *,
        policy: SandboxPolicy,
        receipts: Path,
        runtime: DockerSandboxRuntime | None = None,
    ) -> None:
        self.policy = policy
        self.receipts = receipts
        self.runtime = runtime or DockerSandboxRuntime()

    def execute(self, request: AgentRequest) -> AgentResponse:
        try:
            validate_profile(request.profile)
        except ValueError as error:
            raise AgentExecutionError(str(error)) from error
        with self.runtime.workspace(
            policy=self.policy,
            workspace=request.workspace,
            seconds=request.timeout_seconds,
            label=request.stage.value,
            receipts=self.receipts,
        ) as guest:
            schema = guest.directory / "schema.json"
            schema.write_text(json.dumps(output_schema(request.stage)))
            guest.upload(schema, "/tmp/shipyard-schema.json")
            # Docker's generated provider configuration is required for OAuth routing.
            # No host user config is mounted or copied into this fresh VM.
            command = [
                "codex",
                "exec",
                *request.profile.arguments,
                "--ephemeral",
                "--config",
                'approval_policy="never"',
                "--cd",
                GUEST_REPOSITORY,
                "--model",
                request.profile.model,
                "--sandbox",
                "workspace-write" if request.stage == AgentStage.BUILD else "read-only",
                "--output-schema",
                "/tmp/shipyard-schema.json",
                "--output-last-message",
                "/tmp/shipyard-final.json",
                "--color",
                "never",
                "-",
            ]
            invocation = request.model_copy(
                update={"workspace": Path(GUEST_REPOSITORY)}
            )
            capture = guest.capture(
                command,
                cwd=request.workspace,
                timeout=request.timeout_seconds,
                limit=65536,
                input_bytes=format_prompt(invocation).encode(),
            )
            diagnostics = AgentResponse(
                returncode=capture.returncode,
                output="",
                stdout=capture.stdout.decode("utf-8", errors="replace"),
                stderr=capture.stderr.decode("utf-8", errors="replace"),
                stdout_truncated=capture.stdout_truncated,
                stderr_truncated=capture.stderr_truncated,
            )
            if capture.timed_out:
                raise AgentTimeoutError(
                    "Sandboxed Codex timed out", response=diagnostics
                )
            if capture.returncode:
                raise AgentExecutionError(
                    "Sandboxed Codex failed", response=diagnostics
                )
            try:
                final = guest.download(
                    "/tmp/shipyard-final.json",
                    guest.directory / "final.json",
                    limit=4 * 1024 * 1024,
                ).decode("utf-8")
            except (OSError, UnicodeError) as error:
                raise AgentExecutionError(
                    "Cannot read sandboxed Codex output", response=diagnostics
                ) from error
            guest.export_changes(build=request.stage == AgentStage.BUILD)
            return diagnostics.model_copy(update={"output": final})
