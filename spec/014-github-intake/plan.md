# Plan

1. Write focused tests first; observe missing-adapter import failure.
2. Implement the gh Adapter as a small function following the Markdown boundary,
   keeping provider output parsing outside the domain. Add common source dispatch.
3. Verify exact arguments, authoritative normalization and launch/process/output
   failure paths with a small subprocess fake. Include label transport metadata;
   confirm strict metadata rejection fails, then allow irrelevant metadata.
4. Document semantics and run pytest, Ruff and Pyright before committing.
