# Plan

1. Write focused request/output tests and observe missing boundary failure.
2. Add small Pydantic records and a consumer-focused Protocol under agents.
3. Reuse existing stage result models; expose a provider-neutral output schema.
4. Run full validation and commit this slice.

NativeAgent is an Adapter boundary: provider process details stay outside stage
orchestration without adding a provider registry or class hierarchy.
