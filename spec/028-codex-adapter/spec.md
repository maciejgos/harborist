# Specification: Codex process adapter

- AC-001: CodexAgent implements NativeAgent through a fresh `codex exec` process
  per call, never resume/fork. Supply prompt on stdin, explicit workspace/model,
  ephemeral mode, stage schema and a fresh final-message file. Read only the final
  message as structured output, never infer success from stdout or prose.
- AC-002: DESIGN, PLAN and REVIEW use read-only repository sandbox; BUILD uses
  workspace-write. Disable approval prompts. Reject non-Codex profiles and profile
  arguments that can override invocation, sandbox, workspace or output controls.
  Initially support only model_reasoning_effort via --config/-c KEY=VALUE.
- AC-003: Prompt contains exact frozen upstream text, selected guidance,
  methodology/profile identities, stage duties, candidate context and remaining
  budget. Markdown outputs are returned in the final JSON envelope, allowing
  read-only stages to produce artifacts through Shipyard.
- AC-004: Missing executable, nonzero process exit, timeout, missing/oversized or
  invalid UTF-8 final message raises AgentExecutionError. Enforce supplied timeout
  and best-effort terminate the process group. Temporary schema/output files are
  removed after each invocation; no raw transcript is retained.
- AC-005: Use a fake executable for real subprocess integration without external
  credentials. Verify invocation semantics and failure cases. Document supported
  Codex CLI flags and the absence of a live provider smoke test.
