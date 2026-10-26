"""Frozen Markdown metadata binds version identity without granting authority."""

from dataclasses import FrozenInstanceError

import pytest

from shipyard.playbooks import MethodologyError, parse_playbook, parse_skill
from tests.methodology_helpers import asset, playbook_asset, skill_asset


def test_parse_preserves_content_and_binds_version_identity() -> None:
    source = playbook_asset()
    document = parse_playbook(source)
    assert document.definition.version == source.version
    assert document.guidance == "# Canonical guidance\n"
    assert document.identity.sha256 == source.sha256
    skill = parse_skill(skill_asset(body="# Café\r\nGuidance\r\n"))
    assert skill.guidance == "# Café\r\nGuidance\r\n"
    assert skill.metadata.id == "engineering"
    assert skill.metadata.version == "1"
    field = "guidance"
    with pytest.raises(FrozenInstanceError):
        setattr(skill, field, "Changed")
    changed = parse_skill(skill_asset(body="Different guidance"))
    assert changed.identity != skill.identity
    assert changed.identity.version == skill.identity.version


@pytest.mark.parametrize(
    "mutation",
    [
        "no-header",
        "duplicate",
        "identity",
        "topology",
        "hook",
        "test-scope",
        "duplicate-scope",
        "body",
    ],
)
def test_skill_rejects_invalid_authority_and_document(mutation: str) -> None:
    source = skill_asset()
    content = source.content
    if mutation == "no-header":
        content = "# Plain legacy Markdown"
    elif mutation == "duplicate":
        content = content.replace("id: engineering", "id: engineering\nid: engineering")
    elif mutation == "identity":
        content = content.replace("id: engineering", "id: other")
    elif mutation == "topology":
        content = content.replace("description:", "depends_on: []\ndescription:")
    elif mutation == "hook":
        content = content.replace("description:", "hooks: [execute]\ndescription:")
    elif mutation == "test-scope":
        content = content.replace("- design", "- test")
    elif mutation == "duplicate-scope":
        content = content.replace("- build", "- design")
    else:
        content = content[: content.rindex("---") + 3] + "\n  \n"
    with pytest.raises(MethodologyError) as caught:
        parse_skill(asset(name=source.name, version=source.version, content=content))
    assert caught.value.__cause__ is not None


@pytest.mark.parametrize("label", ["true", "0", "-1"])
def test_rejects_invalid_version_labels(label: str) -> None:
    source = skill_asset()
    with pytest.raises(MethodologyError):
        parse_skill(
            asset(
                name=source.name,
                version=source.version,
                content=source.content.replace("version: 1", f"version: {label}"),
            )
        )


def test_playbook_metadata_cannot_reassign_test_executor() -> None:
    source = playbook_asset()
    with pytest.raises(MethodologyError):
        parse_playbook(
            asset(
                name=source.name,
                version=source.version,
                content=source.content.replace("trusted_test", "native_agent"),
            )
        )
