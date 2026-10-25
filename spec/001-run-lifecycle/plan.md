# Plan: Run lifecycle foundation

## Approach

1. Record the manually prepared intent and acceptance contract before code.
2. Bootstrap Python 3.14 with uv, Hatchling, a `src/shipyard/` package, and
   Pydantic v2. Add pytest, Ruff (default lint rules, Python 3.14 target), and
   strict Pyright for source and tests. Pin Python and commit `uv.lock`.
3. Implement and export RunLifecycle, RunOutcome, FailureReason, Run, and
   InvalidRunTransition from `shipyard.domain`.
4. Add parametrized invariant and transition tests, then document setup.

## Domain interface

Run is a frozen Pydantic model with `run_id: UUID`, `lifecycle` (default CREATED),
optional `outcome`, and optional `failure_reason`. Reject extra fields. An after
validator enforces state consistency and rejects VERIFIED.

`Run.create()` generates UUID4. `start()`, `complete(outcome)`, `fail(reason)`,
and `cancel()` return validated new instances with the same ID. Explicit source
state guards raise InvalidRunTransition (a ValueError subclass); invalid model
data raises Pydantic validation errors. Failure before start permits future
configuration errors. No unchecked `model_copy` is used by transitions.

## Verification mapping

- AC-001: `uv sync`, full pytest, Ruff, and strict Pyright.
- AC-002: creation, identity preservation, original preservation, frozen fields.
- AC-003/005: exhaustive lifecycle/outcome/reason combinations.
- AC-004: every lifecycle against every operation, including terminal repeats.
- AC-006: VERIFIED construction/completion rejection and TEST_FAILED completion.
- AC-007: valid JSON round-trips and invalid structured input tests.
- AC-008/009: source and documentation review.

Run focused domain tests while iterating, then `uv run pytest`,
`uv run ruff check .`, and `uv run pyright` from the repository root.

## Defaults and exclusions

No CLI entry point or Typer/Rich/PyYAML dependencies yet. No stage-result files
or claims of independent stage execution. Follow the scope boundaries in spec.md.
