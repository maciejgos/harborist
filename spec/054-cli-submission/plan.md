# Implementation plan

Reuse source capture and execution-context resolution. Make run submit locators to the service by default and retain --foreground for synchronous output/exit-code compatibility. Report connection failures with a service-start command and retained UUID. Update existing synchronous tests explicitly; add focused default-submission tests.

Validation: focused red → green tests, then full pytest, Ruff and Pyright.
