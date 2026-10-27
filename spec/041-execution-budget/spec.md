# Specification: Execution budget accounting

- AC-001: Measure Run elapsed time using an injected monotonic clock; record UTC start/end, duration, original and remaining budget without counting PACKAGE.
- AC-002: DESIGN, PLAN and BUILD share the execution allowance excluding the frozen verification reserve. TEST and REVIEW may use the remaining total budget. Exhaustion prevents further work and raises an explicit budget error.
- AC-003: Stage records include timing even when execution fails. Unused time rolls forward; invalid clock measurements fail closed.
