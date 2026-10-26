# Plan

1. Add focused filesystem tests and observe the missing-store import failure.
2. Implement exclusive directory reservation and compose existing intent storage;
   write contract.json last. Validate all stored records and agreement on load.
3. Verify round-trip, overwrite rejection, inconsistent records and injected disk
   failure with retained evidence. Do not retest Git or source adapters here.
4. Document storage/recovery boundaries and run full pytest, Ruff and Pyright.

Simple composition fits existing boundaries; no new pattern or store framework.
