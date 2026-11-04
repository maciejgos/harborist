# AGENTS.md

Shipyard is a local, single-user MVP with a background execution service, CLI client and read-only browser monitor. The execution core remains synchronous. Phase 10 is complete; rework/recovery and GitHub publication remain later phases. Read `ARCHITECTURE.md` before making structural changes.

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

## TDD and test scope

- For behavior changes, follow red → green → refactor: write a focused test, confirm it fails for the intended reason, implement the smallest correct change, then refactor with tests passing.
- For bug fixes, start with a regression test that reproduces the defect. Derive feature tests from acceptance criteria and observable behavior.
- Prefer representative cases, boundary cases, and meaningful failure paths. Use exhaustive combinations only when each combination exercises a distinct rule, such as lifecycle transitions.
- Keep parametrization small and purposeful. Avoid Cartesian products of independent fields and repeated assertions of the same invariant through every API path.
- Test domain rules and integration boundaries. Avoid tests that merely mirror implementation details or recheck library behavior without a Shipyard-specific requirement.
- Use small fakes at external boundaries when useful; verify real Git, filesystem, and subprocess behavior with focused integration tests when those integrations are implemented.
- Documentation-only and mechanical changes do not require new tests. Keep existing required validation checks; test count is not a quality target.

## SOLID and code structure

- **Single responsibility:** Keep domain rules, orchestration, I/O adapters, and CLI presentation separate. Give each module a cohesive reason to change.
- **Open/closed:** Extend established boundaries for concrete requirements. Introduce new extension points when current use cases justify them.
- **Liskov substitution:** Implementations of a boundary must preserve its contract, invariants, and failure semantics. Keep provider-specific behavior behind its adapter.
- **Interface segregation:** Define small, consumer-focused interfaces. Avoid broad service objects that make callers depend on unrelated capabilities.
- **Dependency inversion:** Keep domain code independent of infrastructure. Inject external capabilities through the existing boundaries using explicit constructors or function parameters.
- Prefer clear functions, composition, and small typed records. Add inheritance, protocols, or shared base classes only when they simplify an actual dependency or shared contract.

## GoF design patterns

- Apply a pattern to solve an observed design problem, and explain its benefit in the implementation plan or change description when introducing it.
- Prefer patterns that fit existing boundaries: Adapter for native agents and external tools, Strategy for genuinely interchangeable behavior, and Factory when construction requires validation or derived values.
- Start with the simplest implementation. A function, mapping, or constructor is sufficient when it expresses the behavior clearly; pattern names do not require class hierarchies.
- Keep the canonical workflow explicit. Introduce State, Command, Observer, or other patterns only when their additional structure makes current behavior easier to understand and verify.
- Avoid global mutable state, Singleton-based dependencies, generic plugin frameworks, and speculative layers for future MVP/Product requirements.

## Architecture rules

- Keep execution local: one background service runs one Run at a time through the synchronous execution core. Preserve explicit foreground compatibility and the read-only browser adapter. Do not introduce databases, remote workers, team access or other broader infrastructure unless explicitly requested.
- Preserve the canonical flow: `INTAKE → DESIGN → PLAN → BUILD → TEST → REVIEW → PACKAGE`.
- `DESIGN`, `PLAN`, `BUILD`, and `REVIEW` use fresh native-agent invocations. Do not rely on agent-session continuity.
- `TEST` is trusted Shipyard-controlled execution, not an agent decision. A failed mandatory check prevents `REVIEW`.
- `REVIEW` evaluates the exact candidate revision independently.
- `spec.md` is the acceptance contract. `BUILD` may update `plan.md`, but must not silently change `spec.md`.
- Verification belongs to an exact Git commit SHA. Never transfer verification to changed code.
- Workflow state comes from validated machine-readable results, never inferred from prose.
- Keep persistence filesystem-based for the current MVP. Queue delivery state and observational UI progress must remain distinct from validated Run lifecycle/outcome and exact-revision verification.

## Integration boundaries

- Access coding agents through the `NativeAgent` abstraction; Codex CLI is the first adapter.
- Use the system `git` executable through the Git abstraction rather than introducing a separate Git implementation.
- Use subprocess execution for external tools and deterministic checks.
- Keep provider-specific and CLI-specific details outside the domain model.

## Scope

Prefer the smallest change that preserves these boundaries. Phase 10 covers the local background control plane and read-only monitor. Do not implement Phase 11 rework/recovery, Phase 12 publication or Product Milestone 1 infrastructure unless the task explicitly requires it.
