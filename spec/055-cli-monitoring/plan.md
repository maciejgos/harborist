# Implementation plan

Add runs and status commands over ControlClient. Human and JSON views read persisted delivery data. --wait polls until a delivery terminal state and never mutates or cancels execution. Successful reads exit zero independently of software outcome.

Validation: focused red → green tests, then full pytest, Ruff and Pyright.
