# Validation

The initial focused integration regression failed because BUILD process context
was not persisted. After implementation, coverage verifies durable records despite
truncated diagnostics, optional REVIEW propagation and its input digest, rejection
of foreign Attempt data before invocation, stage authority, bounded excerpts, and
legacy responses. Reported green checks cannot override failed trusted TEST or an
UNVERIFIED criterion explicitly requiring independent historical proof.

Full validation: 629 tests passed; Ruff clean; Pyright clean.

## Live version-pilot replay

- Run: `a1a17f84-a787-4638-aa92-0412b06127b5`.
- Frozen target base: `b967f54366a39a34e72b9818883e0c2dfb139ff1`.
- Candidate: `6b4fc62df9455cc029012d4779e1b7cfe1cd5687`.
- Original version-option issue, same model and 1800/300-second budget, fresh
  invocation/Run/workspace, engineering guidance v2.
- Result: VERIFIED; trusted TEST reported 628 target-project tests, Ruff and
  Pyright passing. All eight product criteria passed independent REVIEW.
- BUILD stderr was truncated. Its separate process artifact nevertheless retained
  six agent-reported check records, including intended red exit 1 and green exit 0.
- REVIEW consumed that artifact's exact SHA-256 and explicitly distinguished the
  declarations from independent proof of historical execution order.
- DESIGN kept TDD policy in a development-process section, rather than inventing
  a historical-proof product criterion. Explicit requirements were not removed
  from any frozen existing spec.

The new harness ran from this uncommitted working-tree implementation. This is a
live integration smoke test, not a new release attestation or statistical rerun
of the paired comparison. The VERIFIED candidate is the version-option target
change; the harness improvement is validated by the repository regression suite.

The original packaged historical Run still loads with the extended models and
retains CHANGES_REQUIRED. Its evidence was not rewritten.

Raw evaluation artifacts and candidate bundles are not retained in this repository.
The replay observations above are a historical summary, not reproducible evidence
shipped with this change.
Independent chronology proof remains outside this slice: these records are
explicitly agent-reported, never trusted Shipyard-controlled test receipts.
