# Browser Run submission and control

The operator can submit, cancel, supersede, rework, and recover a Run from
the workspace. Each action uses the same application rules as its CLI
counterpart.

## Acceptance criteria

- Submit a Run from Markdown or a GitHub issue. Show the repository, source,
  and execution settings before submission. The service freezes the contract
  and returns the Run identity for navigation.
- For rework and recovery, show the selected predecessor, required reason or
  feedback, and applicable time grant before approval. Show the new Attempt
  once accepted.
- For cancellation and supersession, identify the affected Run and describe
  the effect before approval. Supersession captures independent replacement
  intent and links the resulting Run.
- Preserve form input on actionable errors. If admission fails after the
  Run changes, refresh the Run and explain the rejection. A retried
  submission must respect the service's duplicate-request semantics.
- In a packaged browser build, submit a Run, inspect a failed mandatory
  check, and start an eligible rework Attempt. Exercise recovery from an
  eligible execution failure separately.

## Implementation

The workspace offers New Run, Cancel Run, Supersede, Rework, and Recover
dialogs. Writes require the loopback Host, matching Origin, a workspace
request header, and bounded JSON. The service reuses the application capture
function and existing queue admission and retirement commands. Create-only
receipts bind capture retries to their original inputs and Run ID. Continuation
uses the expected predecessor and existing request ID semantics.
