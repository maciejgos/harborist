# Run cancellation

An explicit local service request records the OS operator, UTC timestamp, bounded reason, and the latest available Attempt and stage. Queued work cannot be claimed. Active work checks for cancellation between stages and while native tools or checks are running. The executor stops their process group and packages the cancelled Attempt when possible.

The cancellation record terminates the Run independently of its historical Attempt outcome. Completed evidence and candidate refs remain available. Execution, continuation, and GitHub publication reject retired Runs. Repeating the same request returns the original record.
