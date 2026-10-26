# Specification: Native-agent boundary

- AC-001: Define a synchronous provider-neutral NativeAgent port with one execute
  call per stage and immutable validated request/response records. No session ID,
  resume operation, lifecycle mutation or candidate creation belongs to this port.
- AC-002: Requests bind stage, workspace, frozen profile/guidance, durable input
  text, positive remaining seconds, and optional exact candidate. Guidance must
  match the stage; only REVIEW requires a candidate. Required inputs are intent
  for DESIGN; intent/spec for PLAN; intent/spec/plan for BUILD; spec/test evidence
  for REVIEW. Input names are unique and content is nonblank.
- AC-003: Responses separate process return code from final structured JSON.
  Structured output contains the existing stage result, a Markdown artifact and
  optional BUILD plan revision. Reject malformed JSON, wrong stage, missing/blank
  DESIGN/PLAN/REVIEW artifacts, foreign REVIEW candidates and non-BUILD revisions.
  BUILD does not create a candidate or grant verification.
- AC-004: Publish a stage-specific JSON schema for adapters. No provider types
  enter domain models. Tests cover meaningful contract failures and JSON reload.
