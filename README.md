# Harborist

[harborist.dev](https://harborist.dev)

**Autonomous engineering. Verified delivery.**

Harborist turns engineering requests into independently verified code candidates
with durable evidence. Harborist accepts Markdown or GitHub issues, runs one
request at a time in the background, and lets an operator inspect each Attempt,
recover or rework a Run, and approve publication of the exact verified commit.

## Quick start

Follow the [Docker quickstart](docs/quickstart.md) to start the worker and
browser workspace in containers on Apple silicon macOS. With Docker Sandboxes
selected, Harborist runs agent stages and mandatory checks in fresh VMs on
the host. To run against
your own repository, [configure its mandatory checks and execution
settings](docs/configuration.md).

## Commands

See the complete [CLI command reference](COMMANDS.md) for syntax, options, defaults
and operational requirements.

| Command | Purpose |
| --- | --- |
| `harborist run <source>` | Capture and submit a request. |
| `harborist intake <source>` | Capture frozen inputs without executing. |
| `harborist run <run-id>` | Submit a saved CREATED Run. |
| `harborist rework <run-id> --feedback "..."` | Start a fresh Attempt after rejected software. |
| `harborist recover <run-id>` | Explicitly recover an eligible execution failure. |
| `harborist service serve/start/status/stop` | Manage background execution. |
| `harborist runs` / `harborist status <run-id> --wait` | Inspect saved history and service delivery/results. |
| `harborist web` | Operate the local workspace at http://127.0.0.1:8765. |
| `harborist inspect <run-id>` | Validate and print the frozen contract. |
| `harborist methodology <run-id>` | Preview frozen playbook and skills. |
| `harborist apply <run-id> --branch <branch>` | Apply a packaged VERIFIED candidate. |
| `harborist publish <run-id> --approve <sha> --destination <owner/repo> --base <branch>` | Explicitly publish a VERIFIED candidate to GitHub. |
| `harborist github-status <run-id>` | Fetch and save published PR evidence. |
| `harborist cancel <run-id> --reason "..."` | Record Run cancellation through the service. |
| `harborist supersede <run-id> <source> --reason "..."` | Capture and queue a replacement request. |

Sources accept `file:path/to/issue.md` or `'github:owner/repo#42'`.
Prefix commands with `uv run` from the development checkout. Use
`harborist <command> --help` for options or read the [usage guide](docs/usage.md).

## Workflow

```text
INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE
```

Harborist freezes inputs and configuration, uses fresh native-agent invocations
for DESIGN, PLAN, BUILD and REVIEW, and runs mandatory TEST checks itself.
Verification belongs to the exact candidate commit. PACKAGE writes durable reports
and evidence. Local application and GitHub publication require explicit operator action.

Execution runs locally, serially in the background service or explicitly in the
foreground. Select Docker Sandboxes and edit network/resource policies in
**Integrations → Docker Sandboxes** for a saved Workspace. Docker mode uses fresh
VMs for agents, TEST, and REVIEW. Existing trusted-local settings use Git worktrees,
which isolate workspace state without providing a security boundary. See
[sandbox configuration](docs/configuration.md#docker-sandboxes-execution).

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
- [Run and deliver changes](docs/usage.md)
- [Configuration](docs/configuration.md)
- [Storage and recovery](docs/storage-and-recovery.md)
- [Workflow and verification](docs/methodology.md)
- [Developer reference](docs/developer-reference.md)
