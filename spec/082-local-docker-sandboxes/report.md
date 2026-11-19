# Local Docker Sandboxes implementation verification

Date: 2026-11-19. This verifies the local integration; it does not accept the
remote-worker, lease, or team-governance requirements of Phase 14.

## Automated validation

- Full Python suite: 976 passed. Service/socket tests ran with local socket access.
- Ruff: passed. Pyright: zero errors and warnings.
- Frontend production build: passed. Existing Radix `use client` bundling warnings
  remain informational.
- Documentation links and Git whitespace checks: passed.

## Real execution

Platform: Apple silicon macOS, Docker Sandboxes 0.54.0, Codex 0.170.0,
`gpt-6.2-sol`. The Codex kit is pinned to
`docker.io/sbx/codex@sha256:7d283f7cacf5c069b6f61cdcba87ce3b570a0c5a43c36d88d3f8873732503162`.

A disposable greeting request completed DESIGN, PLAN, BUILD, TEST, REVIEW, and
PACKAGE with VERIFIED. This is a test-repository candidate, not verification
of the Harborist implementation itself:

- Run: `18914a5b-b55b-4045-96a3-de25bf2b3a66`.
- Exact candidate: `9d486e612cb371f0bd694af09ffa77bdeb732f17`.
- Exported bundle SHA-256:
  `101390d7339f541d34b900c097cabc05b24c4c05d116e84ed7660e4f02a5384f`.
- Reconstructed that exact candidate from the exported bundle after VM removal.

Additional real runtime checks confirmed a mandatory command exit code of 7,
cooperative cancellation of a running guest command, and a retained VM inspected
as stopped before removing that disposable test instance. An additional allow
for `example.org:443` permitted its HTTPS request; a sandbox-scoped deny for
`example.com` produced HTTP 403 and curl exit 22. Test VMs were removed by name.

Malformed DESIGN declarations were rejected as INVALID_STAGE_OUTPUT and
packaged without PLAN or BUILD. No repair or inferred success was introduced.
The successful fixture explicitly requested the required declaration syntax.

## Browser verification

The flow was Integrations → Docker readiness → Workspace execution policy →
invalid rule → corrected rules → save → reload. Validation errors omitted the
rejected credential-bearing value; saved CPU/memory and allow/deny counts
reloaded correctly. Chrome through the existing Playwright installation was
used because the Browser plugin was unavailable. Viewports were 1280×900 and
390×844. The app rendered without a framework overlay or JavaScript exception.
Expected invalid-request HTTP 400 and an existing favicon HTTP 404 were the only
console resource errors. The mobile navigation overflow found during testing
was corrected; the final page had no horizontal overflow. Desktop/mobile
screenshots were retained outside the repository.

The design detector reported only the existing Geist font choice. The incumbent
visual system was preserved. The isolated browser-test service was stopped.

## Scope and limits

Preserving Docker's generated `sandboxd` provider configuration is required for
host-managed OpenAI OAuth. Directly reusing trusted-local's
`--ignore-user-config` invocation produced HTTP 401; the sandbox adapter keeps
the generated configuration while importing no host Codex configuration.

Remote worker loss, leases, Organization credential separation, other operating
systems/runtime versions, and Product storage/retention were not validated or
implemented here. Docker's global policy and the user's real Workspace defaults
were not modified by the implementation/browser tests. Existing trusted-local
execution remains available.
