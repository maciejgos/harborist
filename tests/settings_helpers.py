"""Representative operator settings for filesystem and CLI acceptance."""

from pathlib import Path

from tests.methodology_helpers import playbook_asset, skill_asset


def write_settings(root: Path) -> Path:
    (root / "playbook.md").write_bytes(playbook_asset().content.encode())
    (root / "skill.md").write_bytes(skill_asset(body="# Skill\r\n").content.encode())
    path = root / "settings.yaml"
    path.write_text(
        "version: 1\n"
        "playbook: {name: bounded-repository-change, version: '1', path: playbook.md}\n"
        "skills: [{name: engineering, version: '1', path: skill.md}]\n"
        "agent_profile:\n"
        "  name: local-codex\n  version: '1'\n  provider: codex\n"
        "  model: operator-selected-model\n  arguments: []\n"
        "sandbox_policy: trusted-local\n",
        encoding="utf-8",
    )
    return path
