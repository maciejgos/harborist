"""Docker Sandboxes adapter. No host mounts, global policy writes, or host fallback."""

import hashlib
import json
import os
import re
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from uuid import uuid4

from shipyard.agents.base import AgentExecutionError, AgentTimeoutError, NativeAgent
from shipyard.domain.sandbox import SandboxPolicy
from shipyard.execution.cancellation import cancellation_check
from shipyard.execution.process import ProcessCapture, capture_process
from shipyard.git.command import run_git
from shipyard.git.repository import GitReadError

GUEST_REPOSITORY = "/home/agent/workspace/repository"


def policy_digest(raw: bytes) -> str:
    """Exclude IDs and display metadata, retaining all effective global rules."""
    data = json.loads(raw)
    untyped_rules: object = data["rules"]
    if not isinstance(untyped_rules, list) or not untyped_rules:
        raise ValueError("Docker network policy is not initialized")
    rules = cast(list[dict[str, object]], untyped_rules)
    relevant = [
        {
            key: item.get(key)
            for key in (
                "scope",
                "resource_type",
                "decision",
                "resources",
                "actions",
                "status",
                "origin",
                "layer",
                "reason",
            )
        }
        for item in rules
        if item.get("scope") == "global"
    ]
    if not relevant:
        raise ValueError("No global Docker policy")
    return hashlib.sha256(
        json.dumps(
            sorted(relevant, key=lambda item: json.dumps(item, sort_keys=True)),
            sort_keys=True,
        ).encode()
    ).hexdigest()


class DockerSandboxRuntime:
    def __init__(self, *, executable: str = "sbx") -> None:
        self.executable = executable

    def agent(self, *, policy: SandboxPolicy, receipts: Path) -> NativeAgent:
        from shipyard.agents.sandbox import SandboxCodexAgent

        return SandboxCodexAgent(policy=policy, receipts=receipts, runtime=self)

    def control(self, *args: str, timeout: float = 10) -> bytes:
        try:
            result = subprocess.run(
                [self.executable, "--no-input", *args],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode:
                raise ValueError(
                    "Docker Sandboxes command failed. Check Docker login, runtime service, and network policy in your terminal."
                )
            return result.stdout
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError(
                "Docker Sandboxes is unavailable in the service environment. Install sbx and restart the service."
            ) from error

    def baseline_digest(self) -> str:
        version = self.control("version").decode("utf-8")
        if not re.search(r"\bv0\.54\.\d+\b", version):
            raise ValueError("This adapter requires Docker Sandboxes 0.54.x.")
        try:
            return policy_digest(self.control("policy", "ls", "--json"))
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                "Docker Sandboxes returned an unsupported policy format."
            ) from error

    def check(self) -> dict[str, object]:
        try:
            digest = self.baseline_digest()
            return {
                "status": "ready",
                "message": "Docker Sandboxes 0.54.x is available with an initialized network policy. Model credentials are checked when execution starts.",
                "baseline_sha256": digest,
            }
        except ValueError as error:
            return {"status": "unavailable", "message": str(error)}

    def require_policy(self, policy: SandboxPolicy) -> None:
        try:
            actual = self.baseline_digest()
        except ValueError as error:
            raise AgentExecutionError(str(error)) from error
        if policy.baseline_sha256 is None or actual != policy.baseline_sha256:
            raise AgentExecutionError(
                "Docker network policy changed since intake. Capture a new Run with the current policy."
            )

    @contextmanager
    def workspace(
        self,
        *,
        policy: SandboxPolicy,
        workspace: Path,
        seconds: float,
        label: str,
        receipts: Path,
    ) -> Generator[DockerWorkspace]:
        sandbox = DockerWorkspace(self, policy, workspace, seconds, label, receipts)
        token = None
        try:
            sandbox.prepare()
            yield sandbox
        finally:
            # Cancellation must not skip VM termination and removal.
            token = cancellation_check.set(None)
            try:
                sandbox.close()
            finally:
                cancellation_check.reset(token)


class DockerWorkspace:
    def __init__(
        self,
        runtime: DockerSandboxRuntime,
        policy: SandboxPolicy,
        workspace: Path,
        seconds: float,
        label: str,
        receipts: Path,
    ) -> None:
        self.runtime = runtime
        self.policy = policy
        self.host = workspace
        self.deadline = time.monotonic() + seconds
        self.name = f"shipyard-{label}-{uuid4().hex[:16]}"
        self.receipts = receipts
        self.started = False
        self.revision = run_git(workspace, "rev-parse", "HEAD").decode().strip()
        self.record: dict[str, object] = {
            "name": self.name,
            "stage": label,
            "revision": self.revision,
            "policy": policy.model_dump(mode="json"),
            "exported": False,
            "removed": False,
        }
        self.temporary = TemporaryDirectory(prefix="shipyard-sandbox-")
        self.directory = Path(self.temporary.name)

    def allowance(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTimeoutError("Docker Sandboxes execution deadline exhausted")
        return remaining

    def cli(
        self,
        *args: str,
        input_bytes: bytes = b"",
        limit: int = 65536,
        timeout: float | None = None,
    ) -> ProcessCapture:
        environment = os.environ.copy()
        for key in (
            "SSH_AUTH_SOCK",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            environment.pop(key, None)
        result = capture_process(
            [self.runtime.executable, "--no-input", *args],
            cwd=self.directory,
            timeout=min(self.allowance(), timeout) if timeout else self.allowance(),
            limit=limit,
            input_bytes=input_bytes,
            env=environment,
        )
        if result.timed_out:
            raise AgentTimeoutError("Docker Sandboxes command timed out")
        return result

    def require(
        self, *args: str, input_bytes: bytes = b"", limit: int = 65536
    ) -> bytes:
        result = self.cli(*args, input_bytes=input_bytes, limit=limit)
        if result.returncode or result.stdout_truncated:
            raise AgentExecutionError(
                "Docker Sandboxes operation failed or exceeded the transfer limit"
            )
        return result.stdout

    def prepare(self) -> None:
        self.runtime.require_policy(self.policy)
        self.started = True
        self.record["runtime_version"] = self.require("version").decode("utf-8").strip()
        self.require(
            "create",
            "--name",
            self.name,
            "--cpus",
            str(self.policy.cpus),
            "--memory",
            f"{self.policy.memory_mib}m",
            "--skills",
            "off",
            "--static-mcp",
            "none",
            self.policy.template,
        )
        for decision, resources in (
            ("allow", self.policy.allow),
            ("deny", self.policy.deny),
        ):
            for resource in resources:
                self.require(
                    "policy", decision, "network", "--sandbox", self.name, resource
                )
        bundle = self.directory / "source.bundle"
        run_git(self.host, "bundle", "create", str(bundle), "HEAD")
        self.upload(bundle, "/tmp/shipyard-source.bundle")
        self.require(
            "exec",
            self.name,
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "clone",
            "--no-checkout",
            "/tmp/shipyard-source.bundle",
            GUEST_REPOSITORY,
        )
        self.git(
            "-c", "core.hooksPath=/dev/null", "checkout", "--detach", self.revision
        )

    def upload(self, path: Path, destination: str) -> None:
        self.require("cp", str(path), f"{self.name}:{destination}")

    def download(self, source: str, destination: Path, *, limit: int) -> bytes:
        self.require("cp", f"{self.name}:{source}", str(destination))
        if (
            destination.is_symlink()
            or not destination.is_file()
            or destination.stat().st_size > limit
        ):
            raise AgentExecutionError("Sandbox output is not a bounded regular file")
        return destination.read_bytes()

    def git(self, *args: str, limit: int = 65536) -> bytes:
        return self.require(
            "exec",
            self.name,
            "git",
            "--no-replace-objects",
            "-C",
            GUEST_REPOSITORY,
            "-c",
            "core.hooksPath=/dev/null",
            *args,
            limit=limit,
        )

    def capture(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout: float,
        limit: int,
        input_bytes: bytes = b"",
    ) -> ProcessCapture:
        del cwd
        remaining = min(timeout, self.allowance())
        result = self.cli(
            "exec",
            "-i",
            "--workdir",
            GUEST_REPOSITORY,
            self.name,
            "timeout",
            "--kill-after=2s",
            f"{max(0.001, remaining):.3f}s",
            *command,
            input_bytes=input_bytes,
            limit=limit,
            timeout=remaining,
        )
        if result.returncode == 125:
            raise AgentExecutionError(
                "Docker Sandboxes could not execute the guest command"
            )
        return ProcessCapture(
            result.returncode,
            result.returncode in (124, 137),
            result.stdout,
            result.stderr,
            result.stdout_truncated,
            result.stderr_truncated,
        )

    def export_changes(self, *, build: bool) -> None:
        if self.git("rev-parse", "HEAD").decode().strip() != self.revision:
            raise GitReadError("Agent changed the exact starting revision")
        flags = self.git("ls-files", "-v", "-z").split(b"\0")
        if any(
            flag and (flag[:1].islower() or flag.startswith(b"S ")) for flag in flags
        ):
            raise GitReadError("Sandbox index tracking was changed")
        self.git("clean", "-f", "-d", "-X", "--", ".")
        self.git("add", "--all", "--", ".")
        patch = self.git(
            "diff",
            "--cached",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            self.revision,
            limit=16 * 1024 * 1024,
        )
        if patch and not build:
            raise GitReadError("Read-only stage or TEST changed the candidate")
        if patch:
            from shipyard.git.command import git_environment

            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.host),
                    "apply",
                    "--index",
                    "--binary",
                    "--whitespace=nowarn",
                    "-",
                ],
                input=patch,
                capture_output=True,
                env=git_environment(),
                check=False,
            )
            if result.returncode:
                raise AgentExecutionError("Cannot import sandbox BUILD changes")
        self.runtime.require_policy(self.policy)
        self.record["exported"] = True

    def require_unchanged(self) -> None:
        self.export_changes(build=False)

    def close(self) -> None:
        try:
            if self.started:
                if self.record["exported"]:
                    self.runtime.control("rm", "--force", self.name, timeout=30)
                else:
                    try:
                        self.runtime.control("stop", self.name, timeout=30)
                    except ValueError:
                        # Creation may have failed before the VM existed; inspection
                        # below still has to prove it is absent or stopped.
                        pass
                remaining = json.loads(self.runtime.control("ls", "--json"))
                retained = next(
                    (item for item in remaining if item["name"] == self.name), None
                )
                if retained is None:
                    self.record["removed"] = True
                elif not self.record["exported"] and retained["status"] == "stopped":
                    self.record["retained"] = (
                        "Export incomplete; stopped for explicit inspection or recovery"
                    )
                else:
                    raise ValueError("Sandbox termination or removal is still pending")
        except ValueError as error:
            self.record["cleanup_error"] = str(error)
            raise AgentExecutionError(
                "Sandbox cleanup failed. Inspect the recorded sandbox identity before retrying."
            ) from error
        finally:
            self.receipts.mkdir(parents=True, exist_ok=True)
            (self.receipts / f"{self.name}.json").write_text(
                json.dumps(self.record, indent=2)
            )
            self.temporary.cleanup()
