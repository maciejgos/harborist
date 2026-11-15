# Draft specification: MVP GitHub delivery and Run control

Source: [PRD §§20–40, 90, 97, and 98](../../docs/Product%20Requirements%20Document%20v1.0.md#90-mvp-definition).

## GitHub publication

- Require a separate explicit operator authorization tied to the exact VERIFIED candidate SHA. Validate the candidate and publication eligibility before any remote mutation.
- Push that SHA without changing the candidate. Create or update a PR with the request, implementation summary, base and candidate SHAs, TEST and REVIEW results, limitations, and a reference to full evidence.
- Block updates when the expected PR head changed. Preserve human changes and leave merge authority with GitHub.
- Exercise stale-head and candidate-integrity failure cases. Each must leave GitHub unchanged.

## GitHub collaboration evidence

- Record PR state, review feedback, bounded CI evidence, current head, and merge provenance separately from historical Shipyard verification.
- Mark a divergent current PR head as unverified by Shipyard. Keep the original candidate's verification even when GitHub CI later fails.
- Allow explicitly selected feedback to guide a fresh rework Attempt under the frozen spec. Human commits used as inputs require fresh verification before publication.

## Run cancellation

- Extend the existing terminal lifecycle and foreground interruption behavior with an explicit operator action through the local service.
- Record the actor, timestamp, reason, Attempt, and stage. Signal active execution, terminate it best-effort, and persist bounded evidence.
- Make cancellation Run-terminal. Retain candidate and evidence history, block further Attempts, and make any unpublished VERIFIED candidate ineligible for publication.
- Cover cancellation of queued work, active work, and a completed Run with an unpublished candidate.

## Run supersession

- Require an explicit replacement action. Link the original Run and its replacement and record the original Run's terminal supersession reason.
- Create the replacement with a newly frozen contract and independent evidence. Preserve the original artifacts and verification as historical records.
- Retain any open PR for human handling and identify it as superseded where appropriate.
- Exercise supersession while the original Run is active and verify that the replacement cannot inherit its verification.
