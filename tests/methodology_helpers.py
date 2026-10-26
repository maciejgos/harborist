"""Small frozen methodology inputs for parsing and engine acceptance."""

import hashlib

import yaml

from shipyard.domain import MethodologyAsset
from shipyard.domain.playbook import canonical_playbook


def asset(*, name: str, version: str, content: str) -> MethodologyAsset:
    return MethodologyAsset(
        name=name,
        version=version,
        content=content,
        sha256=hashlib.sha256(content.encode()).hexdigest(),
    )


def playbook_asset() -> MethodologyAsset:
    definition = canonical_playbook(version="1").model_dump(mode="json")
    header = {"id": definition["name"], "version": 1, "stages": definition["stages"]}
    return asset(
        name="bounded-repository-change",
        version="1",
        content=f"---\n{yaml.safe_dump(header, sort_keys=False)}---\n# Canonical guidance\n",
    )


def skill_asset(
    *,
    name: str = "engineering",
    stages: tuple[str, ...] = ("design", "build"),
    body: str = "# Engineering\nFollow the acceptance contract.\n",
) -> MethodologyAsset:
    header = {
        "id": name,
        "version": 1,
        "description": "Engineering guidance",
        "stages": list(stages),
    }
    return asset(
        name=name,
        version="1",
        content=f"---\n{yaml.safe_dump(header, sort_keys=False)}---\n{body}",
    )
