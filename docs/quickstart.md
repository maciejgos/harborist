# Run Harborist with Docker

Run the Harborist service and browser workspace in local Docker containers.
Select Docker Sandboxes for your Workspace so that each agent stage and
mandatory TEST run in fresh VMs on the host.

## Before you begin

- Run the host commands in Bash. The current installer requires Apple silicon
  macOS with hardware virtualization and Docker Desktop running.
- Install Git, Cargo, and standalone Docker Sandboxes 0.54.x. Check the sandbox
  version with `sbx version`. You can also supply a prebuilt native Harborist
  binary through `HARBORIST_RUST_HELPER`.
- Sign in with `sbx login`, initialize the Docker Sandboxes network policy with
  `sbx policy init` if needed, and configure Codex authentication with
  `sbx secret set openai --oauth`. Run these
  commands on the sandbox host as the same user who starts Harborist.

## 1. Start Harborist

From a Harborist checkout on the deployment host, run:

```bash
./deploy/harborist start
./deploy/harborist exec service status
```

The installer starts the host sandbox helper and two containers. It checks that
the worker can read the host sandbox policy through the helper. Open
[http://127.0.0.1:8765](http://127.0.0.1:8765) to use the browser workspace.

## 2. Register a repository and select Docker Sandboxes

Put the target Git repository in the worker's persistent data directory.
For example, replace `REPOSITORY_URL` in this command with a public Git clone URL:

```bash
docker compose --project-name harborist exec -T service \
  git clone REPOSITORY_URL /home/harborist/.harborist/project
```

The repository must have committed mandatory checks and a settings file
with accessible playbook and skill paths. See [Configure Harborist](configuration.md)
for the file formats.

1. In **Workspaces → New Workspace**, register `/home/harborist/.harborist/project` and select
   its settings file. Enter the container path.
2. In **Integrations → Docker Sandboxes**, choose **Check Docker
   Sandboxes**. Select your Workspace, choose **Edit execution policy**, and
   select **Docker Sandboxes**.
3. Save the policy, then submit a new Run. Harborist freezes the policy at
   intake. Existing Runs keep their captured settings.

## 3. Submit a Run and inspect the result

Use **New Run** in the browser workspace to submit an engineering request.
For Markdown intake, use a request file accessible to the worker, such as a
committed request in the cloned checkout. You can also submit it from the CLI:

```bash
./deploy/harborist exec run file:/home/harborist/.harborist/project/request.md \
  --repo /home/harborist/.harborist/project
./deploy/harborist exec status RUN_ID --wait
```

Replace `RUN_ID` with the returned UUID. Open the Run to inspect trusted checks,
review findings, and the candidate SHA. A `VERIFIED` result applies to that exact
commit. See [Run and deliver changes](usage.md) for delivery and troubleshooting.

Use `./deploy/harborist stop` when you are done. It stops the containers and
the host helper while retaining Run data. See [local container deployment](configuration.md#local-container-deployment)
for upgrades and configuration.

## Run the development checkout directly

Submit a Markdown request from a Harborist development checkout, follow its
progress, and inspect the candidate and verification evidence.

### Before you begin

- Install Git and [uv](https://docs.astral.sh/uv/). uv uses the checkout's
  pinned Python version.
- Install and authenticate Codex CLI with `codex login`. Your account needs
  access to the model in the execution profile. See [Set up local
  Codex](usage.md#set-up-local-codex).
- Use a Harborist checkout and a request you trust. This tutorial selects the
  included `trusted-local` profile so you can run it without Docker Sandboxes.
  Git worktrees isolate checkout state. Local agents and check commands run
  with your OS user's permissions. For VM isolation, see [Docker Sandboxes
  execution](configuration.md#docker-sandboxes-execution).

### Install dependencies and start the service

If you need a development checkout, clone the repository:

```bash
git clone https://github.com/maciejgos/harborist.git
cd harborist
```

From the Harborist repository root, run:

```bash
uv sync
uv run harborist agent check --settings examples/intake/settings.yaml
uv run harborist service start
```

The agent check reports Codex connection and profile status. If either needs
attention, fix it before submitting the request. The service continues running
after the command returns.

### Submit the example request

```bash
uv run harborist run file:examples/intake/issue.md \
  --settings examples/intake/settings.yaml
```

Harborist captures the request and records the base revision, mandatory checks,
and execution settings. The command returns a Run UUID. A successful submission
means the service accepted the Run.

### Follow the Run

Replace `RUN_ID` with the UUID from the previous command.

```bash
uv run harborist status RUN_ID --wait
```

For the browser workspace, run the command below in another terminal and open
[http://127.0.0.1:8765](http://127.0.0.1:8765). Open the Run to see its stage
timeline, mandatory checks, and review findings.

```bash
uv run harborist web
```

### Inspect the outcome

Read the Run outcome and the saved `report.md` and `evidence.json`. A
`VERIFIED` outcome identifies the Git commit that passed both mandatory checks
and independent review. Your branch moves only when you explicitly apply the
candidate.

- **Verified.** Review the evidence, then [apply the candidate
  locally](usage.md#apply-a-verified-candidate) or [publish it to
  GitHub](usage.md#publish-a-verified-candidate-to-github).
- **Checks failed or review requested changes.** Inspect the failed checks or
  criteria, then [start a rework Attempt](usage.md#rework-and-recovery).
- **Execution was interrupted.** Check the delivery and Run status before
  [starting recovery](usage.md#rework-and-recovery).

When you finish, `uv run harborist service stop` requests a graceful shutdown.

### Next steps

[Configure a target repository](configuration.md) to use your own mandatory
checks, agent profile, and sandbox policy. See [Run and deliver
changes](usage.md) for GitHub issue intake and foreground execution.
