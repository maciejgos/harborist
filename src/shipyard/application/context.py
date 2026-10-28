"""Local invocation locators, separate from frozen Run contracts."""

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExecutionContext(BaseModel):
    """Versioned filesystem context for one captured Run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(strict=True)
    run_id: UUID
    repository: Path
    runs_root: Path

    @field_validator("version")
    @classmethod
    def supported_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(
                "Unsupported execution context version; use legacy explicit invocation"
            )
        return value

    @field_validator("repository", "runs_root")
    @classmethod
    def absolute_resolved_path(cls, value: Path) -> Path:
        if not value.is_absolute() or value.resolve() != value:
            raise ValueError("Context paths must be absolute resolved paths")
        return value

    @property
    def path(self) -> Path:
        return self.runs_root / str(self.run_id) / "execution-context.json"

    def save(self) -> Path:
        """Create only; failures retain the capture for explicit legacy execution."""
        try:
            with self.path.open("x", encoding="utf-8") as output:
                output.write(self.model_dump_json())
        except OSError as error:
            raise ValueError(
                f"Cannot save execution context {self.path}; capture {self.run_id} is retained. "
                f"Use shipyard run {self.run_id} with --repo {self.repository} "
                f"and --runs-dir {self.runs_root} explicitly"
            ) from error
        return self.path


def load_context(*, path: Path, run_id: UUID) -> ExecutionContext:
    """Fail closed for an explicitly supplied locator; never discover or repair."""
    try:
        context = ExecutionContext.model_validate_json(path.read_bytes())
        if context.run_id != run_id:
            raise ValueError(f"Run identity must match requested Run {run_id}")
        if path.resolve() != context.path:
            raise ValueError(f"Context location must match {context.path}")
        return context
    except (OSError, ValueError, RuntimeError) as error:
        raise ValueError(
            f"Invalid --context {path}: {error}. Supply the original context file "
            "or omit --context and use explicit --repo and --runs-dir"
        ) from error
