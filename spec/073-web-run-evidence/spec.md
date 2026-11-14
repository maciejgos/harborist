# Run detail and evidence

The operator opens a Run directly from its URL or from the inbox. The detail
page puts the current status and the most relevant evidence together, using
the shared workspace design from specification 072.

## Acceptance criteria

- Show the stage timeline and Attempt history. Selecting an earlier Attempt
  shows its own candidate, outcome, and evidence, including for saved Runs.
- Lead with failed mandatory checks and their available output. For a verified
  candidate, show the exact commit SHA with its TEST and REVIEW evidence.
- Present reports, specifications, and bounded logs in readable, keyboard
  accessible views. Identify unavailable and truncated evidence explicitly.
- Keep the selected Run, Attempt, and evidence view stable across live updates.
  An interrupted connection is visible and refreshing restores current data.
