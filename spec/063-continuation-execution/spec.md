# Specification: Rework and recovery execution

- AC-001: Execute fresh native-agent calls using the existing synchronous executor and NativeAgent boundary. Reuse validated frozen DESIGN only; run PLAN and BUILD afresh with bounded feedback and prior plan, candidate, TEST and REVIEW context.
- AC-002: Use fresh detached worktrees and immutable attempt candidate refs; preserve first-attempt compatibility. Descendant candidates start at the previous candidate, never a moving target branch.
- AC-003: Package each terminal attempt independently with exact candidate TEST/REVIEW and explicit reused-spec provenance. Failed mandatory checks block REVIEW. Enforce cumulative budget across repeated continuations.
