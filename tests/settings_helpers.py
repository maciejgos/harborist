"""Representative operator settings for filesystem and CLI acceptance."""

from pathlib import Path


def write_settings(root: Path) -> Path:
    (root / "playbook.md").write_text("# Canonical playbook\n", encoding="utf-8")
    (root / "skill.md").write_bytes(b"# Skill\r\n")
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
