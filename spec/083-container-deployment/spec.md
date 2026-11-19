# Local container deployment

An operator can install and run Shipyard locally using a single deployment
command. The service and browser UI share a small Linux image. Local Docker
Sandboxes microVMs run on the host using the existing 0.54.x integration.
The service still owns one Run at a time and stores its state on disk.

## Acceptance criteria

- **AC-1 · Runtime image.** Use a multi-stage build with digest-pinned inputs,
  Python 3.14, and locked production dependencies. Use the smallest supported
  base that can run Shipyard and system Git on Linux arm64 and amd64. Use
  Alpine when locked wheels and system Git are available. Record the final
  image size on each supported architecture. Keep build tooling, development dependencies, and local
  credentials out of the final image. Run as a non-root user.
- **AC-2 · Compose lifecycle.** Run the service and web UI from the same image
  with distinct entry commands. Share the Unix control socket and preserve
  queue state, workspaces, and evidence across container replacement. Publish
  the browser port on host loopback and preserve Host and same-origin guards.
  Use a service health check. Restarting the web UI has no effect on an active
  Run. Repository paths used for intake and execution resolve consistently
  within the service and container CLI.
- **AC-3 · Host sandbox control.** Provide a host-side helper for the existing
  sandbox adapter operations, including readiness, frozen-policy checks,
  create, per-VM policy, guest execution, bundle and artifact transfer, stop,
  and removal. Use a private authenticated transport. Validate every operation
  and verify deployment ownership for each sandbox. Confine host file access
  to helper-owned staging and bound transfer size, output size, and execution
  time. Reject arbitrary host commands, host mounts, external sandbox IDs, and
  global policy writes. No service or web container mounts the Docker socket.
  Keep Docker and Codex authentication under host operator control.
- **AC-4 · Run semantics.** Preserve mountless fresh VMs, independent TEST
  and REVIEW, exact candidate verification, and existing cancellation and
  retained-VM receipts. Helper unavailability or version/policy drift fails
  closed. Cancellation stops the VM, and restarting either side does not
  authorize cleanup of unrelated VMs. Existing native installation and
  foreground entry points continue to work.
- **AC-5 · Unified installer.** A repeatable host command checks Docker,
  Compose, virtualization and the supported sbx version, sets up the helper
  and persistent storage, and starts the stack. It reports required operator
  sign-in and Codex credential setup without collecting credentials. The first
  supported host is Apple silicon macOS. Document start, stop, upgrade,
  supported repository registration, and removal while preserving Run data.
- **AC-6 · CI and supply chain.** Keep the existing validation checks. On
  pull requests and main, scan repository dependencies, configuration and
  secrets with Trivy and scan the built runtime image. Block detected secrets
  and high or critical findings with a fix available. Fail if the scanner
  cannot complete. Pin scanner and build images by digest and actions by
  full commit SHA. Use least-privilege CI tokens. Export the image with its
  BuildKit SBOM and provenance, tied to the source commit. CI requires no
  sandbox credentials and publishes no image to a registry.

## Validation

Run the full repository checks. In CI, start the Compose services and verify
the browser assets, web-to-service health, Host rejection and persistence
after container replacement. Test the helper with rejected requests,
interrupted transfers, lost connections and cancellation. On the supported
host, submit a disposable repository through the deployed service, verify
the exact packaged candidate and fresh VM receipts, and demonstrate mandatory
TEST failure and cancellation without leaving running VMs. Record the image
size and real runtime evidence in the implementation report.
