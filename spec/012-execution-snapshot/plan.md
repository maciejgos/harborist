# Plan

1. Extend Run contract tests first and confirm execution is rejected by the old
   schema (observed seven focused failures).
2. Add small frozen domain records and require their composition in RunContract.
3. Cover meaningful budget boundaries, content integrity, canonical methodology,
   unique skills and immutable round-trips. Preserve existing binding tests.
4. Update current documentation and run pytest, Ruff and Pyright before committing.

No new design pattern is needed: typed record composition expresses the contract.
