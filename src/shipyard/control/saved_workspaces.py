"""Local saved checkout and execution defaults."""

import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shipyard.configuration import load_execution_settings
from shipyard.control.workspace import normalize_path
from shipyard.domain import ExecutionBudget
from shipyard.git import GitRepository
from shipyard.persistence.application import ensure_record_directory
from shipyard.skills import compile_methodology
from shipyard.verification import load_verification_config

GITHUB_REPOSITORY = r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+"


class WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: UUID
    name: str = Field(min_length=1, max_length=100)
    repository: Path
    settings: Path | None = None
    ref: str = Field(default="HEAD", min_length=1, max_length=256)
    timeout: int = Field(default=1800, gt=0, strict=True)
    verification_reserve: int = Field(default=300, gt=0, strict=True)
    github_repository: str | None = Field(default=None, max_length=256)


class WorkspaceStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list(self) -> list[WorkspaceSettings]:
        return sorted(
            (
                WorkspaceSettings.model_validate_json(path.read_bytes())
                for path in self.directory.glob("*.json")
            ),
            key=lambda workspace: (workspace.name.casefold(), workspace.id),
        )

    def get(self, workspace_id: UUID) -> WorkspaceSettings:
        try:
            workspace = WorkspaceSettings.model_validate_json(
                (self.directory / f"{workspace_id}.json").read_bytes()
            )
        except FileNotFoundError as error:
            raise ValueError("Workspace was not found") from error
        if workspace.id != workspace_id:
            raise ValueError("Workspace identity mismatch")
        return workspace

    def save(self, workspace: WorkspaceSettings) -> WorkspaceSettings:
        repository = GitRepository(
            path=normalize_path(workspace.repository, "Repository path")
        )
        checkout = repository.checkout_root()
        base = repository.resolve_base(ref=workspace.ref)
        load_verification_config(repository=repository, base_sha=base)
        path = (
            normalize_path(workspace.settings, "Settings path")
            if workspace.settings
            else None
        )
        budget = ExecutionBudget(
            total_seconds=workspace.timeout,
            verification_reserve_seconds=workspace.verification_reserve,
        )
        execution = load_execution_settings(
            path=path or checkout / "shipyard.settings.yaml", budget=budget
        )
        compile_methodology(execution)
        if workspace.github_repository and not re.fullmatch(
            GITHUB_REPOSITORY, workspace.github_repository
        ):
            raise ValueError("GitHub repository: enter owner/repository")
        saved = workspace.model_copy(update={"repository": checkout, "settings": path})
        ensure_record_directory(self.directory)
        with NamedTemporaryFile(dir=self.directory, delete=False) as stream:
            pending = Path(stream.name)
            try:
                stream.write(saved.model_dump_json().encode())
                stream.close()
                pending.replace(self.directory / f"{saved.id}.json")
            finally:
                pending.unlink(missing_ok=True)
        return saved
