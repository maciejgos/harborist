# Implementation plan

Keep workflow policy in execute_run. Worker claims one record, injects NativeAgent and delegates to the existing executor with FileRunStore and system Git. Persist observational progress and distinguish returned evidence from raised delivery failures. Verify with real Git/checks and a fake native-agent adapter.

Validation: focused red → green tests, then full pytest, Ruff and Pyright.
