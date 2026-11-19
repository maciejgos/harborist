# Methodology

[Documentation index](README.md) · [Architecture](../ARCHITECTURE.md)

## Canonical playbook definition

`harborist.domain.playbook.canonical_playbook(version="1")` returns an immutable
seven-stage definition with fixed dependencies and executor authority. TEST is
trusted Harborist execution; agent stages require fresh invocations; REVIEW is
read-only and PACKAGE is outside budget. Modified/omitted stages or weakened
metadata are rejected. This defines topology without executing it. See
[canonical playbook specification](../spec/019-canonical-playbook/spec.md).

## Frozen methodology documents

`harborist.playbooks.parse_playbook` and `parse_skill` compile captured assets with
leading YAML front matter. Playbooks declare `id`, `version` and canonical `stages`;
skills declare `id`, `version`, `description` and their agent `stages`. Front-matter
identity must match the frozen asset. Skill metadata cannot declare dependencies,
executors or hooks. Bodies remain exact opaque guidance; no file or tool is read.

Document identities include kind, name, version and exact source SHA-256. Changed
bytes remain distinguishable even when a version label is reused. Legacy plain
Markdown captures can still be inspected, but compilation requires explicit front
matter. See [methodology document specification](../spec/020-methodology-documents/spec.md).

## Stage guidance composition

`harborist.skills.compile_methodology(execution)` parses all frozen methodology
inputs. `compose_guidance(compiled, stage=ArtifactStage.BUILD)` selects skills for
the requested agent stage in configured order. It returns immutable sections with
exact bodies, descriptions and content-bound identities. A stage may have no
matching skills. INTAKE/TEST/PACKAGE cannot receive agent skill composition.

Guidance is kept separate from the playbook's control metadata. Prose never
changes dependencies or executor authority. Phase 4 implements provider prompt
formatting and invocation. See [stage guidance specification](../spec/021-stage-guidance/spec.md).

## Playbook routing

`PlaybookExecution(playbook=definition, attempt=attempt)` starts with INTAKE as its
next stage. `accept(StageReceipt(...))` returns a new immutable execution only when
the receipt matches the required stage and Candidate/Attempt identity. Successful
routing cannot skip TEST; a failed TEST routes to PACKAGE and blocks REVIEW.
Failures, cancellation and early exits also retain PACKAGE outside budget. PACKAGE
ends routing even if packaging fails. Validated JSON reloads enforce the same rules.

Receipts must come from trusted orchestration after actual executor validation.
They are declarations, not proof that checks ran or review passed; this engine
performs no I/O and does not grant VERIFIED. See the
[routing specification](../spec/022-playbook-routing/spec.md).

## Bundled methodology

Harborist includes canonical playbook v1 and engineering skill v2, scoped to all
four agent stages. The standalone files under `examples/intake`
match the package resources. `harborist.skills.defaults.load_default_methodology()`
returns frozen assets independently of the caller's working directory; an explicit
agent profile is still required when adopting them into an execution snapshot.
No existing Run is migrated. See [bundled methodology specification](../spec/023-bundled-methodology/spec.md).
