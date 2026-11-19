# Local container deployment validation

Validated on 2026-11-19 with Docker Engine 29.9.3 and Docker Sandboxes 0.54.0
on Apple silicon macOS. Compose smoke tests passed for Linux arm64 and emulated
Linux amd64. Both tests reached the service through the web port, downloaded
browser assets, verified rejection of a foreign Host and Origin, and preserved
state through replacement of both containers.

The builds use Python 3.14 on Alpine 3.23, locked Python wheels, system Git,
and a non-root runtime user. Compressed runtime layers were 30.01 MiB for arm64
and 29.73 MiB for amd64. Both OCI archives contained SPDX SBOM and SLSA provenance
attestations. Alpine serves signed package updates during the build, so the
fixed base digest and Python lock do not make builds bit-for-bit reproducible.
Trivy repository and runtime image scans passed at the configured thresholds.
A hosted GitHub Actions run is pending.

## Host helper and installer

The installer started the user-scoped launchd helper, worker and browser UI,
and checked the worker's authenticated connection to the host's sbx runtime.
An initial restart exposed a race while launchd unloaded the old job. The
installer now retries bootstrap for a bounded interval. The start and repeat
start sequence passed, and the worker recovered the earlier Run's bundle.

sbx reported a stable UUID in its inventory, and guest execution required
the sandbox name. The helper records the UUID and compares it against the
live inventory before operating on that name. Focused tests cover wrong
credentials, incomplete transfer requests, connection loss during execution,
the mountless allowlist, guest argument separation, and rejection of reused
names after restart.

## Real Run

The disposable greeting Run `201a13ba-b3e8-4d66-af9f-cf9ecbcf9f16` reached
VERIFIED on candidate `a31fd0a16b226f6334cd7e0f8b92ef30b153d8cc` through the
containerized worker. Its five receipts identify distinct fresh VMs, all
removed. TEST and REVIEW both identify the verified SHA. After restarting the
deployment, a checkout reconstructed from the exported bundle had that exact
HEAD and the expected file bytes. The bundle SHA-256 was
`793e7f59d4dabbafb5126a03e95994c3caec8466b895eec9073726e969415a1a`.

The mandatory-failure Run `6e14c5fb-e8de-478f-9053-336a7203ed3b` packaged
`TEST_FAILED` with trusted command exit code 7. REVIEW was skipped, no
verification was recorded, and the TEST VM was removed.

During Run `1cfab30f-a126-45cc-9498-c2e6b54f95c8`, the web container was
restarted while the mandatory TEST command was still running. The service
continued TEST. Cancellation then reached the `CANCELLED` lifecycle, packaged
the available evidence, and retained the TEST VM stopped with a cleanup receipt.
The host inventory showed no running sandboxes. The browser API also registered
and reloaded the same persistent repository path used by the deployed CLI.
Removing the disposable deployment unloaded the helper and removed its
containers while preserving both named volumes.

The final local validation passed with 992 pytest tests, Ruff, Pyright,
both architecture image scans and smoke tests, and Git whitespace checks.

CI now checks the OCI archive before upload. The check requires an SPDX SBOM
and SLSA provenance whose subjects match the runtime image digest. It compares
the image label and recorded build argument to the workflow commit. The
verifier accepted an archive built from a disposable local commit and rejected
the same archive when given a different revision.
