# Shipyard

Shipyard is a local, evidence-driven delivery harness for native coding agents. It turns an engineering request into an independently verified, revision-bound code candidate with durable evidence.

> **Status:** Phase 8 complete: synchronous CLI execution, revision-bound
> verification, bounded logs, shared budget accounting and terminal reports/evidence.
> Phase 9 baseline evaluation remains ahead.

## Quick start

Install [uv](https://docs.astral.sh/uv/). Shipyard pins Python 3.14; uv downloads
it if needed. Install and authenticate Codex CLI before executing agent stages.
GitHub Issue input also requires an installed, authenticated `gh`.
The target repository must have committed mandatory checks in `shipyard.yaml`
and local operator configuration in `shipyard.settings.yaml`; this checkout
includes both. See [configuration](docs/configuration.md) for another repository.

From this development checkout:

```bash
uv sync
uv run shipyard run file:examples/intake/issue.md
```

The command captures the request, executes the workflow in an isolated Git
worktree, and prints the outcome and report/evidence paths. Review those results.
For a VERIFIED Run, apply its candidate to an existing local branch explicitly:

```bash
uv run shipyard apply <run-id> --branch <existing-local-branch>
```

Application requires the branch to be eligible for advancement. See
[applying a verified candidate](docs/usage.md#apply-a-verified-candidate).

## Commands

| Command | Purpose |
| --- | --- |
| `shipyard run <source>` | Capture and execute a request. |
| `shipyard intake <source>` | Capture frozen inputs without executing. |
| `shipyard run <run-id>` | Execute a saved CREATED Run. |
| `shipyard inspect <run-id>` | Validate and print the frozen contract. |
| `shipyard methodology <run-id>` | Preview frozen playbook and skills. |
| `shipyard apply <run-id> --branch <branch>` | Apply a packaged VERIFIED candidate. |

Sources accept `file:path/to/issue.md` or `'github:owner/repo#42'`.
Prefix commands with `uv run` from the development checkout. Use
`shipyard <command> --help` for options or read the [usage guide](docs/usage.md).

## Workflow

```text
INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE
```

Shipyard freezes inputs and configuration, uses fresh native-agent invocations
for DESIGN, PLAN, BUILD and REVIEW, and runs mandatory TEST checks itself.
Verification belongs to the exact candidate commit. PACKAGE writes durable reports
and evidence; applying a candidate is a separate user operation.

The PoC runs locally and synchronously. Git worktrees isolate workspace state;
they do not provide hostile-code isolation.

## Development

Run from the repository root:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

See [AGENTS.md](AGENTS.md) for repository working instructions.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture](ARCHITECTURE.md)
- [Usage](docs/usage.md)
- [Configuration](docs/configuration.md)
- [Storage and recovery](docs/storage-and-recovery.md)
- [Methodology](docs/methodology.md)
- [Developer reference](docs/developer-reference.md)
