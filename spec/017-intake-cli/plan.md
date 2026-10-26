# Plan

1. Write CLI round-trip/failure tests and confirm the missing-app import failure.
2. Add the architecture-selected Typer dependency and entry point; keep CLI parsing,
   terminal output and exit handling outside application/domain code.
3. Reuse settings/test helpers and add runnable input/configuration examples.
4. Verify CLI help and installed/module entry points, full pytest, Ruff and Pyright.
5. Commit this slice before the independent Phase 2 acceptance-audit slice.
