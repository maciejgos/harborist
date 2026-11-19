# Plan

1. Test a fake Codex executable across repeated independent calls and failure paths.
2. Implement an Adapter using subprocess argument arrays and per-call temporary
   files; retain only the final structured message, with a size bound.
3. Build prompts from explicit requests. Restrict profile arguments so caller
   settings cannot weaken Harborist-owned invocation controls.
4. Verify timeout cleanup, run full checks and commit.

Reference: https://learn.chatgpt.com/docs/developer-commands#codex-exec and local
`codex exec --help` checked 2026-10-26. No model names or provider SDKs are embedded.
