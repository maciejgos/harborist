# Plan

1. Add focused routing tests and observe missing-engine import failure.
2. Implement a small immutable history record and explicit replay function for the
   single canonical workflow. No generic State hierarchy or command framework.
3. Test happy path, mandatory TEST gating, exact Candidate/Attempt binding,
   early exits/cancellation and terminal PACKAGE, plus validated JSON recovery.
4. Document the trusted-receipt boundary and run full validation before committing.
