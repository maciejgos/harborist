"""Translate deployment requests into an allowlisted local sbx invocation."""

import re

from shipyard.domain.sandbox import CODEX_KIT, SandboxPolicy
from shipyard.sandbox.docker import GUEST_REPOSITORY

_NAME = re.compile(r"shipyard-(?:design|plan|build|test|review)-[a-f0-9]{16}")
_UPLOADS = frozenset(("/tmp/shipyard-source.bundle", "/tmp/shipyard-schema.json"))
_DOWNLOAD = "/tmp/shipyard-final.json"


def host_command(args: tuple[str, ...], *, owned: set[str]) -> tuple[str, ...]:
    if any("\x00" in value for value in args):
        raise ValueError("Invalid sandbox command argument")

    match args:
        case ("version",) | ("policy", "ls", "--json") | ("ls", "--json"):
            return args
        case (
            "create",
            "--name",
            name,
            "--cpus",
            cpus,
            "--memory",
            memory,
            "--skills",
            "off",
            "--static-mcp",
            "none",
            template,
        ) if _NAME.fullmatch(name) and name not in owned and template == CODEX_KIT:
            if not re.fullmatch(r"[0-9]{1,2}", cpus) or not re.fullmatch(
                r"[0-9]{3,5}m", memory
            ):
                raise ValueError("Invalid sandbox resources")
            SandboxPolicy(cpus=int(cpus), memory_mib=int(memory[:-1]))
            return args
        case (
            "policy",
            ("allow" | "deny"),
            "network",
            "--sandbox",
            name,
            destination,
        ) if name in owned:
            (normalized,) = SandboxPolicy.network_resources((destination,))
            return (*args[:-1], normalized)
        case ("stop", name) | ("rm", "--force", name) if name in owned:
            return args
        case ("exec", "-i", "--workdir", directory, name, executable, *rest) if (
            directory == GUEST_REPOSITORY and name in owned
        ):
            return ("exec", "-i", "--workdir", directory, "--", name, executable, *rest)
        case ("exec", name, executable, *rest) if name in owned:
            return ("exec", "--", name, executable, *rest)
        case ("upload", name, path) if name in owned and path in _UPLOADS:
            return ("exec", "-i", "--", name, "dd", f"of={path}", "status=none")
        case ("download", name, path) if name in owned and path == _DOWNLOAD:
            return ("exec", "--", name, "cat", path)
        case _:
            raise ValueError("Sandbox operation is outside this deployment's authority")
