# Specification: Mandatory check runner

- AC-001: Execute every frozen configured command sequentially in the supplied workspace, including after nonzero exits or launch errors.
- AC-002: Collect immutable ordered results with command identity, exit status, timeout/error and stdout/stderr logs outside the workspace. Success requires every check to exit zero.
- AC-003: Bound each subprocess with an explicit positive timeout; terminate its process group on timeout. Commands use the local POSIX shell, as trusted local configuration.
