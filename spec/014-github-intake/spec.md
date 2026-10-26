# Specification: GitHub Issue intake and common source dispatch

- AC-001: Accept github:owner/repo#positive-number, validate before subprocess, and
  invoke gh issue view once with explicit --repo and title,body,labels JSON fields.
  Use the local authenticated environment, argument-list execution and 30s timeout.
- AC-002: Require string title/body and labels with string names. Ignore additional
  label transport metadata. Normalize to '# {title}\n\nLabels: {sorted JSON names}
  \n\n{body}', preserving body content, deduplicating/sorting names, excluding comments.
  Record the original validated selector as source_ref in IntentSnapshot.
- AC-003: Invalid selectors, malformed output, missing gh, process errors and timeout
  fail with GitHubIntakeError. Underlying failures remain available as causes.
- AC-004: capture_intent dispatches file:path and github selectors. Unknown/empty
  sources fail clearly. File capture preserves exact UTF-8 including optional
  front matter; normalization means a common snapshot, not rewriting local text.
  Snapshots have no live dependency on subsequent source edits.

No source-repository equality requirement, GitHub writes, comments, or agent calls.
