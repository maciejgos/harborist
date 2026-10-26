# Specification: Independent native-stage execution

- AC-001: A synchronous application function invokes an injected NativeAgent once
  from a reloaded RunContract, Attempt, explicit workspace, durable upstream paths
  and remaining seconds. Compile only frozen methodology. Bind Attempt to Run and
  REVIEW candidate to Attempt. No agent continuity, lifecycle mutation or CLI run
  loop is introduced.
- AC-002: DESIGN consumes frozen intent and returns spec.md; PLAN consumes intent
  and spec.md and returns plan.md; BUILD consumes intent/spec/plan and may return
  a new plan.md. Require nonblank UTF-8 upstream content, exact frozen intent,
  stage-appropriate inputs, and an unchanged spec after BUILD. Persist revised
  plans separately rather than overwriting upstream versions.
- AC-003: REVIEW consumes spec.md and test-evidence.json, and requires a trusted
  successful TEST receipt for its exact candidate. Require a clean workspace at
  that candidate before and after invocation. Use read-only invocation policy and
  reject mismatched review output. This slice does not validate criterion coverage
  or grant VERIFIED; Phase 7 owns semantic acceptance.
- AC-004: Reserve a new output directory outside the workspace before invocation.
  Persist request.json, validated stage-result.json, required Markdown and a final
  manifest with Run/Attempt, candidate, artifact digests/sizes and provenance.
  Never overwrite existing directories. Partial failed captures remain inspectable
  without a success manifest. Successful process and valid output are both required.
- AC-005: Reject upstream changes during any invocation. Invocation errors or
  invalid output cannot produce a successful result or routing receipt. BUILD
  readiness remains separate from Phase 5 candidate creation. Full workflow budget
  accounting, RunStore finalization and trusted TEST execution remain later work.
- AC-006: Tests execute DESIGN→PLAN→BUILD from reloaded files and independent fake
  agents, and REVIEW against real Git. Cover process failure, invalid output,
  upstream mutation, output reuse, failed TEST, foreign candidate and dirty review.
