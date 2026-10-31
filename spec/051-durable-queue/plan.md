# Implementation plan

Use immutable Pydantic submission/record models. QueueStore serializes reads and writes with a filesystem flock, publishes fsynced snapshots by replacement and uses Run UUID as its idempotency key. Claim only QUEUED work and never retry RUNNING or terminal delivery records. Focused tests reproduce duplicate, conflicting, interrupted and corrupt-record paths.

Validation: focused red → green tests, then full pytest, Ruff and Pyright.
