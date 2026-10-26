# Specification: Isolated Git workspaces

- AC-001: Create a fresh detached worktree at an Attempt's exact start SHA using system Git; reject existing destinations and non-commit objects.
- AC-002: Never copy or modify developer staged, unstaged, untracked or ignored files. Reject destinations inside the source checkout.
- AC-003: Preserve repository environment isolation and disable replacement objects. Return an explicit workspace adapter bound to the Attempt. Failed creation must not report success; do not remove partial work automatically.
- AC-004: Real Git tests prove isolation, exact base selection, destination collision and invalid revision failure.
