# AGENTS.md

Shipyard is currently a synchronous, CLI-first PoC. Read `ARCHITECTURE.md` before making structural changes.

## Commands

Run from the repository root:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

While iterating, run the smallest relevant test first, for example:

```bash
uv run pytest tests/path/to/test_file.py
uv run pytest -k "test_name"
```

If formatting is needed:

```bash
uv run ruff format .
```

Before completing a change, run the full validation set:

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## Architecture rules

- Keep the PoC local and synchronous. Do not introduce FastAPI, databases, background workers, web UI, or other MVP/Product infrastructure unless explicitly requested.
- Preserve the canonical flow: `INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE`.
- `DESIGN`, `PLAN`, `BUILD`, and `REVIEW` use fresh native-agent invocations. Do not rely on agent-session continuity.
- `TEST` is trusted Shipyard-controlled execution, not an agent decision. A failed mandatory check prevents `REVIEW`.
- `REVIEW` evaluates the exact candidate revision independently.
- `spec.md` is the acceptance contract. `BUILD` may update `plan.md`, but must not silently change `spec.md`.
- Verification belongs to an exact Git commit SHA. Never transfer verification to changed code.
- Workflow state comes from validated machine-readable results, never inferred from prose.
- Keep persistence filesystem-based for the PoC.

## Integration boundaries

- Access coding agents through the `NativeAgent` abstraction; Codex CLI is the first adapter.
- Use the system `git` executable through the Git abstraction rather than introducing a separate Git implementation.
- Use subprocess execution for external tools and deterministic checks.
- Keep provider-specific and CLI-specific details outside the domain model.

## Scope

Prefer the smallest change that preserves these boundaries. Do not implement future MVP or Product Milestone 1 architecture unless the task explicitly requires it.
