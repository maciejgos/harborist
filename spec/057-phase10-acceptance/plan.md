# Implementation plan

Use real subprocesses and Unix sockets to prove submitting CLI exit, exact-SHA VERIFIED packaging, duplicate submission and forced-kill restart behavior. Replace only the native-agent boundary. Exercise the actual detached service lifecycle commands. Update architecture, quick start, usage and storage documentation, and validate the entire repository.

Validation: focused red → green tests, then full pytest, Ruff and Pyright.
