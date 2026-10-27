# Specification: Revision-bound verification gate

- AC-001: A validated immutable verification record binds Run, exact Candidate, spec reference, complete REVIEW results and mandatory check evidence. It requires nonempty complete passing checks and exactly one PASS for every required criterion.
- AC-002: Run completion with VERIFIED requires that record, matching Run ownership. Construction and JSON reload enforce the same invariants; evidence cannot accompany other outcomes or active states.
- AC-003: Missing, duplicate, foreign or failed criteria/check evidence cannot grant VERIFIED. Existing nonverified lifecycle transitions retain their behavior.
