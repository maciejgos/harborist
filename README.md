# Shipyard

Shipyard is a local, evidence-driven delivery harness for native coding agents. It turns an engineering request into an independently verified, revision-bound code candidate with durable evidence.

> **Status:** PoC design and implementation baseline.

## Workflow

```text
INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE
```

The PoC uses Codex through a native-agent abstraction and provides:

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
