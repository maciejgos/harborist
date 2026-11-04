# Specification: Immutable attempt storage

- AC-001: Keep the original Run directory and terminal evidence readable. Store subsequent attempts in numbered child directories, with fresh lifecycle journals, workspaces and a create-only continuation record linking predecessor and new Attempt identities.
- AC-002: Expose the latest attempt through normal Run reads while retaining explicit historical access. Serialize continuation admission with a local filesystem lock; stale predecessor requests and incomplete admissions fail closed.
- AC-003: Validate predecessor evidence, file digests, attribution and contract before copying durable upstream artifacts. Never copy verification into a new attempt. Retain partial admissions rather than retrying automatically.
