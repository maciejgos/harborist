"""Placement policy separating retained checkouts from controlled Run records."""

from pathlib import Path

from harborist.git.repository import GitWorkspaceError


def validate_workspace_placement(*, path: Path, run_directory: Path) -> Path:
    """Only the dedicated child may live under Runs storage.

    External overrides are allowed, but cannot contain Runs storage. Git's own
    preflight separately validates freshness, access, aliases and source overlap.
    This policy is rechecked immediately before worktree creation.
    """
    try:
        resolved = path.resolve()
        directory = run_directory.resolve()
        root = directory.parent
        dedicated_child = resolved == directory / "workspace"
        # A workspace alias must not redirect traversal away from this child.
        if dedicated_child and (directory / "workspace").is_symlink():
            raise ValueError("Reserved workspace root must not be a symlink")
        if not dedicated_child and (
            resolved.is_relative_to(root) or root.is_relative_to(resolved)
        ):
            raise ValueError("Workspace overlaps Harborist-controlled Run records")
        # Also reject placement under an independently configured Runs root.
        # Inspect ancestors only; never traverse or modify another capture.
        for parent in resolved.parents:
            if dedicated_child and parent == directory:
                continue
            if (parent / "run.json").is_file() and (
                (parent / "contract.json").is_file()
                or (parent / "intent.json").is_file()
            ):
                raise ValueError(f"Workspace overlaps Run records at {parent}")
        return resolved
    except (OSError, ValueError, RuntimeError) as error:
        raise GitWorkspaceError(
            f"Invalid workspace {path}: {error}; supply --workspace with a fresh "
            "external path or the Run's dedicated workspace child"
        ) from error
