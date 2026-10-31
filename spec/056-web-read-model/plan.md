# Implementation plan

Project each queue record into a typed RunView by validating FileRunStore lifecycle and Attempt ownership. Expose lifecycle, outcome, progress, Attempt ID and terminal file references. Missing or transiently inconsistent lifecycle is explicitly unavailable. Do not serve files, infer verification or change execution records.

Validation: focused red → green tests, then full pytest, Ruff and Pyright.
