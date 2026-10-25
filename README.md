# Shipyard

Shipyard is a local, evidence-driven delivery harness for native coding agents. It turns an engineering request into an independently verified, revision-bound code candidate with durable evidence.

> **Status:** PoC domain foundation: Run lifecycle, Attempt, and candidate identity.

## Development

Install [uv](https://docs.astral.sh/uv/), then run from the repository root:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

The project pins Python 3.14. uv will download it if needed. Domain contracts are
available through `shipyard.domain`; the CLI and workflow execution are planned.
The Run lifecycle acceptance contract is in
[spec/001-run-lifecycle/spec.md](spec/001-run-lifecycle/spec.md), alongside its
intake intent and implementation plan. VERIFIED is reserved and rejected until
revision-bound verification is implemented.

`Attempt` identifies one execution within a Run and its starting commit.
`Candidate` identifies an owning Attempt and an exact resulting commit. Both are
immutable records; commit hashes accept full lowercase SHA-1 or SHA-256 syntax.
Repository validation and Git operations are planned. See the
[Attempt and candidate specification](spec/002-attempt-candidate-identity/spec.md)
for the acceptance contract, with intent and implementation guidance alongside it.

## Workflow

```text
INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE
```

The planned PoC uses Codex through a native-agent abstraction and will provide:

- Markdown and GitHub Issue intake;
- isolated Git worktrees;
- deterministic checks defined in `shipyard.yaml`;
- independent semantic review;
- verification bound to an exact candidate commit;
- filesystem-backed evidence and reports.

The PoC runs synchronously on the developer's machine. It uses the local environment and does not provide hostile-code isolation.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Product Requirements Document](docs/Product%20Requirements%20Document%20v1.0.md)
