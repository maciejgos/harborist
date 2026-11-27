# Configure Harborist

Configure the checks Harborist must run for a candidate, then select the agent
profile and execution policy for your checkout.

| File | Purpose |
| --- | --- |
| `harborist.yaml` | Repository-owned mandatory checks, committed at the target Git revision. |
| `harborist.settings.yaml` | Operator-selected playbook, skills, agent profile, and sandbox policy. |

## Mandatory checks

Create `harborist.yaml` at the target repository root. For example, a Python
project managed with uv can require its test suite:

```yaml
version: 1
checks:
  - id: tests
    command: uv run pytest
```

Use check commands that are available in your chosen execution environment.
Each check requires a unique ID and a nonblank command. Configure at least one
check. Commit the file before intake. Harborist reads it from the exact base
commit selected by `--ref`, which defaults to `HEAD`. Uncommitted edits take
effect after you commit them and capture against that revision.

## Operator execution settings

Create `harborist.settings.yaml` at the checkout root or pass an explicit
`--settings PATH` when you capture. This example assumes you have copied the
[example playbook and skill](https://github.com/maciejgos/harborist/tree/main/examples/intake) beside your settings file
and have access to the selected Codex model.

```yaml
version: 1
playbook:
  name: bounded-repository-change
  version: '1'
  path: playbook.md
skills:
  - name: engineering
    version: '2'
    path: engineering.md
agent_profile:
  name: local-codex
  version: '1'
  provider: codex
  model: gpt-6.1-sol
  arguments: []
sandbox_policy: trusted-local
```

The `trusted-local` policy runs agents and commands with your local account's
permissions. Use it for repositories and requests you trust. For VM isolation,
configure [Docker Sandboxes](#docker-sandboxes-execution).

| Setting | How it resolves |
| --- | --- |
| `--repo PATH` | Selects the Git checkout. The default is the current directory. Harborist finds the checkout root from a subdirectory. |
| `--settings PATH` | Selects an explicit settings file relative to the current directory or by absolute path. Without this option, Harborist looks at the target checkout root. |
| Playbook and skill paths | Resolve relative to the selected settings file. Their contents and digests become part of the saved Run. |
| `agent_profile.arguments` | Use `[]` for Codex's default reasoning effort or `['-c', 'model_reasoning_effort="high"']` to choose an effort. Supported values are `minimal`, `low`, `medium`, `high`, and `xhigh`. |

Harborist reports missing or invalid settings before creating the Run. Correct
the selected file or pass a valid `--settings PATH`. To use updated settings
or a different model, capture a new Run. See [Set up local Codex](usage.md#set-up-local-codex)
to check the connection and edit the profile.

## Local container deployment

Follow the [Docker quickstart prerequisites](quickstart.md#before-you-begin)
for the current installer. Run Docker Sandboxes setup as the same host user
who starts Harborist.

From the Harborist checkout, run `./deploy/harborist start`, then open
`http://127.0.0.1:8765`. The installer prepares the host helper and starts
the worker and browser UI. The worker can reach the helper via Docker
Desktop. Only the worker receives its deployment token. Docker and Codex
credentials stay in the host's Docker Sandboxes credential store.

The Rust migration branch provides a separate local deployment for
validation. Set `HARBORIST_DEPLOY_RUNTIME=rust` for each launcher command.
Cargo builds the native Sandbox host helper, or you can supply an absolute
path to a prebuilt native binary with `HARBORIST_RUST_HELPER`. Choose separate
ports when running both deployments.

```sh
export HARBORIST_DEPLOY_RUNTIME=rust HARBORIST_WEB_PORT=18765 HARBORIST_SANDBOX_PORT=19455
./deploy/harborist start
./deploy/harborist exec service status
./deploy/harborist stop
```

The Rust deployment defaults to project `harborist-rust` and helper state
under `~/.local/share/harborist-rust-deployment`.

Keep target repositories in the worker's persistent data directory. For
example, clone a public repository there with:

```sh
docker compose --project-name harborist exec service git clone https://example.org/owner/project.git /home/harborist/.harborist/project
```

Register the container path in the Workspaces screen and select its settings
file. Set its execution policy to Docker Sandboxes with the default pinned
kit before capturing a Run. Container deployment and Workspace execution policy
are configured independently. Use the same paths with the CLI, for example:

```sh
./deploy/harborist exec run file:/home/harborist/.harborist/project/request.md --repo /home/harborist/.harborist/project
```

Run `./deploy/harborist stop` to stop the stack and host helper. After updating
the checkout, run `./deploy/harborist start` to rebuild and restart. The
`./deploy/harborist remove` command removes the running deployment and leaves
the volumes and helper identity in place so you can reinstall without losing
Run data. Set `HARBORIST_WEB_PORT` to select a different loopback port. For an
independent deployment, set a distinct `HARBORIST_DEPLOY_PROJECT`,
`HARBORIST_DEPLOY_STATE`, `HARBORIST_WEB_PORT`, and `HARBORIST_SANDBOX_PORT` for
its lifecycle commands.

See the [deployment specification](../spec/083-container-deployment/spec.md).

## Docker Sandboxes execution

In **Integrations → Docker Sandboxes**, select a Workspace, check readiness,
and choose **Edit execution policy**. Select Docker Sandboxes, set CPU/memory
limits, and edit allowed or blocked destinations, one per line. Save applies to
future Runs using that Workspace's settings file. Shared settings files share
these defaults. You can also edit the version 1 settings YAML:

```yaml
sandbox_policy:
  kind: docker-sandboxes
  cpus: 2
  memory_mib: 2048
  allow:
    - registry.example.com:443
  deny:
    - example.com
```

The default Codex kit is pinned by digest. An advanced `template` override must
also contain an immutable `@sha256:` digest. Do not set `baseline_sha256`
manually: intake captures Docker's machine-policy fingerprint. Sandbox settings
and policy reads fail closed; they never fall back to host execution. Existing
`sandbox_policy: trusted-local` settings and frozen Runs remain compatible.

Install Docker Sandboxes 0.54.x on a supported host, then complete `sbx login`,
initialize a Docker network policy, and configure OpenAI authentication with
`sbx secret set openai --oauth` or `sbx secret set openai`. Run these commands as
the OS user that runs the Harborist service. Restart an already-running Harborist
service after installation/upgrading. Docker Desktop alone does not supply this
standalone runtime. The app readiness check does not spend model allowance.

Workspace rules supplement Docker's existing global and kit policy. Deny rules
take precedence; an additional allow cannot override an existing deny. The app
never edits Docker's global rules. If those rules change after intake, capture
a new Run; queued Runs and continuations cannot silently acquire new authority.
Use hostnames with optional wildcard subdomain prefixes and ports. URLs, CIDRs,
HTTP-path rules, and global allow-all rules are rejected.

Every agent stage, TEST, and REVIEW receives a fresh mountless VM. Only committed
repository state, explicit inputs, and bounded outputs cross the boundary.
BUILD changes return as a Git patch; Harborist commits them and retains a complete
`sandbox/candidate.bundle` and checksum receipt. Runtime receipts under the same
Attempt directory record VM identities, export state, and cleanup. Docker's
generated OAuth configuration is preserved; host Codex configuration is absent.
TEST runs in a new VM, and a mandatory failure still prevents REVIEW.

Cancellation and deadlines stop the guest as well as the host client. A VM whose
outputs could not be exported is retained stopped for explicit inspection; its
receipt names it. Recover into a new Attempt rather than reusing that VM. When
finished inspecting retained data, remove only that named VM with `sbx rm --force
<name>`. Cleanup failures are explicit execution failures.

## Budget accounting

A Run's default execution budget is 1,800 seconds, including 300 seconds
reserved for verification. Set different values when capturing a request:

```bash
harborist intake file:./request.md --timeout 2400 --verification-reserve 600
```

The total must exceed the reserve. Queue time is outside the budget. DESIGN,
PLAN, and BUILD can use the time before the reserve. TEST and REVIEW share
the remaining time, including any unused allowance from earlier stages.
PACKAGE records its time separately. See [Rework and recovery](usage.md#rework-and-recovery)
for cumulative spending and time grants.
