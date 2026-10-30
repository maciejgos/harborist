"""Git adapter failures shared by repository, workspace and application operations."""


class GitResolutionError(ValueError):
    """A commit-ish could not be resolved to a validated full commit identity."""


class GitReadError(ValueError):
    """An exact committed file or checkout could not be read or validated."""


class GitWorkspaceError(ValueError):
    """A workspace or candidate operation failed; partial state is retained."""
