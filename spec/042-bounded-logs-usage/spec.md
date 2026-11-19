# Specification: Bounded logs and usage

- AC-001: Trusted subprocess stdout/stderr are continuously drained with bounded retained bytes; truncation is explicit and never changes check success. Timeouts still terminate process groups best-effort.
- AC-002: TEST supports one shared deadline: later checks are recorded as timed out without invocation after exhaustion, preserving complete collection.
- AC-003: NativeAgent responses optionally carry validated normalized token counters and actual provider charge/currency, plus bounded provider metadata. Missing usage and cost remain unknown; Harborist never estimates charges.
