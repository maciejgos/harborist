# Web workspace and Run inbox

The local operator opens `shipyard web` to see which Runs are active, queued,
or need attention and to find completed work. The workspace uses React and
[shadcn/ui](https://ui.shadcn.com/), with [Linear](https://linear.app/) as the
reference for compact navigation, scannable lists, consistent interaction
patterns, and keyboard ergonomics.

## Acceptance criteria

- The inbox shows Run identity, repository, delivery status, stage when known,
  and validated outcome when available. Search and filters help the operator
  locate current and historical Runs.
- Run links are stable across reloads, and back navigation restores inbox
  context. Refreshes preserve selection, focus, and scroll position.
- Shared components and design tokens cover every MVP screen, including forms,
  dialogs, and evidence views. Each screen supports keyboard operation, visible
  focus, responsive layouts, and readable status cues with text.
- Each applicable screen has designed loading, empty, error, and disconnected
  states. After reconnection, the workspace refreshes from the service.
- Development builds the React frontend into assets packaged with Shipyard.
  The installed browser workspace runs locally without a frontend dev server
  or runtime downloads. Existing monitor reads remain available during rollout.
