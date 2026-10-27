# Specification: Criterion references

- AC-001: Extract a nonempty ordered set of required criteria from explicit `AC-NNN: text` lines, Markdown headings (`## AC-NNN — text`) or list items. IDs have at least three digits; every declared criterion is required in the PoC.
- AC-002: Reject duplicate IDs and empty declarations. Ignore fenced examples and inline prose references; never infer acceptance criteria from prose.
- AC-003: Bind the extracted criteria to the SHA-256 of the exact UTF-8 spec, preserving identity across JSON reload. REVIEW must return exactly these IDs once each; missing or unknown IDs are invalid output.
