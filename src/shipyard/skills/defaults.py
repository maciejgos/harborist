"""Read versioned default assets included with the installed Shipyard package."""

import hashlib
from importlib.resources import files

from shipyard.domain.execution import MethodologyAsset
from shipyard.playbooks import MethodologyError, parse_playbook, parse_skill


def _load(
    package: str, filename: str, name: str, version: str = "1"
) -> MethodologyAsset:
    source = files(package).joinpath(filename).read_bytes()
    return MethodologyAsset(
        name=name,
        version=version,
        content=source.decode("utf-8"),
        sha256=hashlib.sha256(source).hexdigest(),
    )


def load_default_methodology() -> tuple[MethodologyAsset, tuple[MethodologyAsset, ...]]:
    """Return captured defaults; adoption still requires an explicit agent profile."""
    try:
        playbook = _load(
            "shipyard.playbooks",
            "bounded-repository-change.md",
            "bounded-repository-change",
        )
        skill = _load("shipyard.skills", "engineering.md", "engineering", "2")
        parse_playbook(playbook)
        parse_skill(skill)
        return playbook, (skill,)
    except (OSError, ValueError) as error:
        raise MethodologyError("Cannot load bundled methodology") from error
