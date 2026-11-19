import pytest

from shipyard.domain.sandbox import CODEX_KIT
from shipyard.sandbox.host_commands import host_command

NAME = "shipyard-build-0123456789abcdef"
OTHER = "shipyard-build-fedcba9876543210"
CREATE = (
    "create",
    "--name",
    NAME,
    "--cpus",
    "2",
    "--memory",
    "2048m",
    "--skills",
    "off",
    "--static-mcp",
    "none",
    CODEX_KIT,
)


def test_create_uses_only_the_mountless_local_configuration() -> None:
    assert host_command(CREATE, owned=set()) == CREATE
    with pytest.raises(ValueError):
        host_command((*CREATE, "/Users/operator"), owned=set())
    with pytest.raises(ValueError):
        host_command(CREATE, owned={NAME})


def test_guest_flags_are_separated_from_host_flags() -> None:
    assert host_command(("exec", NAME, "echo", "--env-file=/host"), owned={NAME}) == (
        "exec",
        "--",
        NAME,
        "echo",
        "--env-file=/host",
    )
    with pytest.raises(ValueError):
        host_command(("exec", "--env-file", "/host", NAME, "env"), owned={NAME})


@pytest.mark.parametrize(
    "command",
    [
        ("stop", OTHER),
        ("rm", "--force", OTHER),
        ("policy", "allow", "network", "example.org"),
        ("policy", "allow", "network", "--sandbox", OTHER, "example.org"),
        ("policy", "allow", "network", "--sandbox", NAME, "--cloud"),
        ("cp", "/Users/operator/.ssh", f"{NAME}:/tmp/key"),
        ("--cloud", "ls", "--json"),
    ],
)
def test_host_permissions_are_scoped_to_owned_sandboxes(
    command: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        host_command(command, owned={NAME})


def test_guest_transfers_use_stdio_and_fixed_guest_paths() -> None:
    assert host_command(
        ("upload", NAME, "/tmp/shipyard-source.bundle"), owned={NAME}
    ) == (
        "exec",
        "-i",
        "--",
        NAME,
        "dd",
        "of=/tmp/shipyard-source.bundle",
        "status=none",
    )
    assert host_command(
        ("download", NAME, "/tmp/shipyard-final.json"), owned={NAME}
    ) == ("exec", "--", NAME, "cat", "/tmp/shipyard-final.json")
    with pytest.raises(ValueError):
        host_command(("download", NAME, "/tmp/../etc/passwd"), owned={NAME})
