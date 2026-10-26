# Specification: Stage guidance composition

- AC-001: compile_methodology validates the complete frozen ExecutionSnapshot and
  parses its playbook and all ordered skills without rereading any source file.
- AC-002: compose_guidance accepts compiled methodology and a stage. Only native
  agent stages are eligible. Select skills whose declared scope includes that
  stage, retaining configured order; an empty selection is valid.
- AC-003: Return immutable structured guidance with stage, playbook identity/body
  and separate skill identity/description/body sections. Preserve exact body text;
  do not merge it into workflow metadata or interpret prose as control state.
- AC-004: Composition is deterministic and has no I/O, executor calls, lifecycle
  transitions, mutation or workflow changes. Even skill prose requesting a skipped
  stage cannot change the canonical playbook or TEST authority.

Provider prompt formatting and invocation are Phase 4. This is composition of
validated data, not enforcement of language-model obedience or a generic plugin API.
