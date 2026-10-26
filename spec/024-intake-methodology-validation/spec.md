# Specification: Methodology validation at intake

- AC-001: create_run compiles the complete supplied frozen execution methodology
  before Git resolution, issue capture or storage. Invalid playbook topology,
  plain legacy methodology and invalid skills fail through MethodologyError.
- AC-002: Valid new captures preserve exact original asset text/digests/versions;
  compilation performs no live reread, mutation or executor invocation.
- AC-003: Historical Phase 2 contracts remain loadable/inspectable as captures;
  they are not silently rewritten or upgraded. Compiling plain legacy methodology
  reports an explicit error. FileRunStore's storage/schema contract is unchanged.
- AC-004: Existing file/GitHub, frozen-base and CLI tests use valid versioned
  methodology fixtures. Rejection must publish no Run directory.

The settings loader remains a byte-capture adapter. Orchestration owns the new
compilation gate; this avoids coupling configuration adapters to engine execution.
