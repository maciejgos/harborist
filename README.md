# Shipyard

Shipyard is a local, evidence-driven delivery harness for native coding agents. It turns an engineering request into an independently verified, revision-bound code candidate with durable evidence.

> **Status:** PoC domain foundation, local intake/persistence, Git base resolution, frozen verification configuration, and a complete in-memory Run contract.

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
Commit resolution is available through `GitRepository`; candidate creation and
workspace operations remain planned. See the
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
normalization, YAML metadata extraction, GitHub/CLI intake, and the complete frozen
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

## Git base resolution

Resolve committed HEAD or a native Git commit-ish through system Git:

```python
from shipyard.git import GitRepository

repository = GitRepository(path=Path("."))
base_sha = repository.resolve_base()
earlier_sha = repository.resolve_base(ref="HEAD~1")
```

The adapter returns a validated full commit SHA, accepts commit tags and native
revision expressions, and rejects non-commit targets. It preserves developer
branches, index, and working files. Repository-scoped environment overrides are
cleared in the subprocess while normal Git configuration is retained.
`GitResolutionError` preserves launch/process/output failures as causes.

Each explicit call resolves afresh. Later Run creation must resolve once and
persist the SHA; this adapter does not freeze a Run contract, create worktrees,
or manage candidate commits/refs. See the
[Git base resolution specification](spec/009-git-base-resolution/spec.md).

## Frozen verification configuration

Target repositories commit a narrow `shipyard.yaml`:

```yaml
version: 1
checks:
  - id: tests
    command: pytest
```

Every listed check is mandatory. At least one check is required; IDs must be
unique and commands nonblank. Unknown fields, unsupported versions, duplicate YAML
keys, and unsafe object tags are rejected. Command strings retain their exact text.

```python
from shipyard.verification import load_verification_config

base_sha = repository.resolve_base()
verification = load_verification_config(repository=repository, base_sha=base_sha)
```

The loader reads the root `shipyard.yaml` from that exact commit, ignoring index
and working-tree edits. Its immutable snapshot retains validated settings, base
SHA, and a SHA-256 of the original file bytes. Git replacement refs cannot substitute
other content for committed-file reads. YAML source text is not retained.

`VerificationConfigError` reports read/parsing/validation failures with causes.
Checks are not executed, and Run outcomes are not changed. TEST execution,
configuration persistence, and the full frozen Run contract remain planned. See
the [verification configuration specification](spec/010-verification-config/spec.md).

## Frozen Run contract

Compose the previously captured inputs without repeating intake or Git resolution:

```python
from shipyard.domain import RunContract

contract = RunContract(
    run_id=run.run_id,
    intent=intent,
    base_sha=base_sha,
    verification=verification,
    execution=execution,
)
serialized = contract.model_dump_json()
restored_contract = RunContract.model_validate_json(serialized)
```

The immutable contract requires matching intent Run ownership and verification
base SHA. Equivalent validated values, including the same existing identities,
produce identical compact JSON regardless of input mapping key order. Exact
Markdown, check order, command text, and provenance survive round-trips.

The required `ExecutionSnapshot` freezes playbook/skill names, versions, exact
content and SHA-256 digests, an explicit agent profile, trusted-local policy, and
an execution budget with a verification reserve. Skill names must be unique;
only the canonical `bounded-repository-change` playbook is supported. Empty skill
lists are explicit. The reserve must be positive and smaller than the total.

This domain record performs no I/O or execution and does not grant verification.
Old partial contracts without execution settings are rejected. Settings loading,
contract persistence, one-contract-per-Run enforcement and intake orchestration
remain planned; Phase 2 is not yet complete. See the
[execution snapshot specification](spec/012-execution-snapshot/spec.md).

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
