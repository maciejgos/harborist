"""Copyable CLI execution commands."""

import shlex
from pathlib import Path
from uuid import UUID

from shipyard.paths import runs_root


def execution_command(
    run_id: UUID, runs_dir: Path, workspace: Path | None = None
) -> str:
    arguments = ["shipyard", "run", str(run_id)]
    if runs_dir != runs_root().resolve():
        arguments += ["--runs-dir", str(runs_dir)]
    if workspace is not None:
        arguments += ["--workspace", str(workspace)]
    return shlex.join(arguments)
