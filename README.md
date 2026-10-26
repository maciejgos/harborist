# Shipyard

Shipyard is a local, evidence-driven delivery harness for native coding agents. It turns an engineering request into an independently verified, revision-bound code candidate with durable evidence.

> **Status:** PoC domain foundation, local Markdown intake, and create-only filesystem intent persistence.

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

DESIGN, PLAN, BUILD, and REVIEW have immutable structured output contracts.
`parse_stage_result` validates a complete JSON document against its expected stage
without repairing output or inferring readiness from prose. REVIEW records an
exact Candidate and per-criterion assessments, with derived summary counts.
Process success, artifact existence, execution-context matching, and verification
remain separate responsibilities; parsing output does not advance a Run or grant
VERIFIED. See the
[stage-result specification](spec/003-stage-result-contracts/spec.md).

`ArtifactReference` records an immutable artifact version with Run/optional Attempt
ownership, kind, producing stage, SHA-256, and byte size. Its factory hashes exact
in-memory bytes without storing content or accessing files. Origin is declared
metadata; storage, integrity verification, and lineage are planned. See the
[artifact identity specification](spec/004-artifact-identity/spec.md).

`RunEvent` and `AttemptCreatedEvent` describe lifecycle facts using immutable
validated snapshots. Factories generate event IDs and require explicit aware
timestamps, normalized to UTC. `DomainEvent` supports discriminated JSON validation
through Pydantic's `TypeAdapter`. Records do not emit events, establish historical
ordering, or change domain state; persistence and full cancellation audit metadata
are planned. See the [domain event specification](spec/005-domain-events/spec.md).

## Markdown intake

Capture a local issue file through the Python API:

```python
from pathlib import Path

from shipyard.domain import Run
from shipyard.intake import read_markdown_intent

run = Run.create()
intent = read_markdown_intent(run_id=run.run_id, path=Path("issue.md"))
```

`IntentSnapshot` preserves exact UTF-8 content, including front matter, BOM, and
line endings, with a validated artifact digest/size and resolved source reference.
Later file edits or deletion do not change the snapshot. Empty content is accepted;
actionability is a later DESIGN decision. `MarkdownIntakeError` wraps file and
UTF-8 decoding errors with their original causes.

This API returns an in-memory capture and leaves the Run unchanged. Semantic
normalization, YAML metadata extraction, GitHub/CLI intake, and the full frozen
Run contract are planned. See the
[Markdown intake specification](spec/007-markdown-intake/spec.md).

## Intent persistence

Save a snapshot under an explicitly supplied Runs directory:

```python
from shipyard.persistence import FileIntentStore

store = FileIntentStore(root=Path(".shipyard/runs"))
store.save(intent)
restored = store.load(intent.run_id)
```

Each Run gets `<root>/<run-id>/intent.md` with exact UTF-8 content and `intent.json`
with source/artifact metadata. Loading validates content digest, size, and Run
ownership without consulting the original issue. Artifact identities are preserved.

Saves are create-only: any existing intent file causes `IntentAlreadyExistsError`,
even for identical content. Metadata is written last. Failed writes may leave
partial files; subsequent loads reject them and saves preserve them for inspection.
`IntentPersistenceError` wraps I/O and invalid stored-data failures with causes.

This store does not provide full Run persistence, automatic repair, atomic
multi-file publication, or power-loss durability guarantees. See the
[intent persistence specification](spec/008-intent-persistence/spec.md).

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
- [Phase 1 acceptance audit](spec/006-phase1-acceptance-audit/report.md)
