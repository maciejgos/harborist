# Shipyard

Shipyard is a local, evidence-driven delivery harness for native coding agents. It turns an engineering request into an independently verified, revision-bound code candidate with durable evidence.

> **Status:** Phase 10 local background control plane implemented around the
> synchronous, revision-bound execution core, including a lightweight browser
> execution monitor. Phase 9 baseline evaluation remains
> outstanding; see the [service guide](docs/background-control-plane.md).

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
uv run shipyard service start
uv run shipyard run file:examples/intake/issue.md
```

The command captures and queues the request, then returns its Run ID. The
service executes independently of the terminal. Run `uv run shipyard web` in
another terminal to follow stage progress visually at http://127.0.0.1:8765.
View the result with
`uv run shipyard status <run-id> --wait`, or use `run --foreground` for
synchronous execution and terminal result exit codes. Review the report/evidence.
For a VERIFIED Run, apply its candidate to an existing local branch explicitly:

```bash
uv run shipyard apply <run-id> --branch <existing-local-branch>
```

Application requires the branch to be eligible for advancement. See
[applying a verified candidate](docs/usage.md#apply-a-verified-candidate).

## Commands

| Command | Purpose |
| --- | --- |
| `shipyard run <source>` | Capture and submit a request. |
| `shipyard intake <source>` | Capture frozen inputs without executing. |
| `shipyard run <run-id>` | Submit a saved CREATED Run. |
| `shipyard service start/status/stop` | Manage background execution. |
| `shipyard runs` / `shipyard status <run-id> --wait` | Inspect saved history and service delivery/results. |
| `shipyard web` | Watch execution at http://127.0.0.1:8765. |
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

Execution runs locally, serially in the background service or explicitly in the
foreground. Git worktrees isolate workspace state;
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
