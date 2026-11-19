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
            raise ValueError("Unsupported execution context version")
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
                f"Use harborist run {self.run_id} with --repo {self.repository} "
                f"and --runs-dir {self.runs_root} explicitly"
            ) from error
        return self.path


def load_context(*, path: Path, run_id: UUID) -> ExecutionContext:
    """Validate a selected explicit or automatic locator; never repair."""
    try:
        context = ExecutionContext.model_validate_json(path.read_bytes())
        if context.run_id != run_id:
            raise ValueError(f"Run identity must match requested Run {run_id}")
        if path.resolve() != context.path:
            raise ValueError(f"Context location must match {context.path}")
        return context
    except (OSError, ValueError, RuntimeError) as error:
        raise ValueError(f"Invalid execution context {path}: {error}") from error


def resolve_context(
    *,
    run_id: UUID,
    repo: Path | None = None,
    runs_dir: Path | None = None,
    context: Path | None = None,
    default_root: Path | None = None,
) -> tuple[Path, Path]:
    """Shared automatic/explicit locator resolution; only absence permits fallback."""
    from harborist.git.repository import GitRepository
    from harborist.paths import runs_root

    selected_root = (
        runs_dir
        if runs_dir is not None
        else (default_root if default_root is not None else runs_root())
    ).resolve()
    selected_context = context
    if selected_context is None:
        automatic = selected_root / str(run_id) / "execution-context.json"
        try:
            automatic.lstat()
        except FileNotFoundError:
            pass
        except OSError as error:
            raise ValueError(
                f"Invalid execution context {automatic}: {error}"
            ) from error
        else:
            selected_context = automatic
    if selected_context is None:
        return GitRepository(
            path=repo if repo is not None else Path(".")
        ).checkout_root(), selected_root
    locator = load_context(path=selected_context, run_id=run_id)
    if repo is not None:
        try:
            matches = GitRepository(path=repo).checkout_root() == locator.repository
        except ValueError as error:
            raise ValueError(
                f"Conflicting --repo {repo}; expected {locator.repository}: {error}"
            ) from error
        if not matches:
            raise ValueError(
                f"Conflicting --repo {repo}; expected {locator.repository}"
            )
    if runs_dir is not None and selected_root != locator.runs_root:
        raise ValueError(
            f"Conflicting --runs-dir {runs_dir}; expected {locator.runs_root}"
        )
    root = GitRepository(path=locator.repository).checkout_root()
    if root != locator.repository:
        raise ValueError(
            f"Saved repository no longer identifies checkout {locator.repository}"
        )
    return root, locator.runs_root
