# Operate the local service

The local service queues Runs and executes one Run at a time. It runs under
your OS account and stays active when you close the submitting terminal or
browser workspace.

The examples use an installed `harborist` command. From a development checkout,
prefix it with `uv run`. For the container deployment, manage the stack with
`./deploy/harborist start` and `./deploy/harborist stop`. Run commands such as
`./deploy/harborist exec service status` inside the worker via the deployment
script. See [Run Harborist with Docker](quickstart.md).

## Start and stop the service

```bash
harborist service start
harborist service status
harborist service stop
```

| Command | Behavior |
| --- | --- |
| `service start` | Starts a detached process and waits for readiness. Repeating it for a healthy service is safe. |
| `service serve` | Runs the service in the current process for a terminal or process supervisor. |
| `service status` | Reports the service's health, including whether it is stopping. |
| `service stop` | Requests a graceful shutdown. The service stops accepting and claiming work, lets the active Run finish, and preserves queued work. |

`stop` returns after requesting the drain. Wait until the service has stopped
before starting it again. SIGINT and SIGTERM also request a drain. Give a
supervised process time to finish the Run's execution budget and package its
evidence.

The service inherits the environment of the launching process. After installing
agent tools or changing credentials or environment variables, let active work
finish and restart the service from the updated environment.

## Open the browser workspace

With the service running, open the workspace in a separate terminal:

```bash
harborist web
```

Visit [http://127.0.0.1:8765](http://127.0.0.1:8765). Use **New Run** to submit a
request, or open a Run to inspect its timeline, evidence, and earlier Attempts.
Close the browser or stop the web command when you are done viewing.

Use `harborist web --port 8766` if the default port is occupied. To choose a
different service, use the same `--control-dir PATH` for the service and its
clients. The browser adapter listens on loopback, and service clients use a
Unix socket accessible to the local account.

## Interpret delivery state

```bash
harborist runs
harborist status RUN_ID --wait
```

Replace `RUN_ID` with the UUID returned when you submitted the request. The
delivery state tracks the queue. The Run outcome describes the software and
verification result.

| Delivery state | Meaning |
| --- | --- |
| `QUEUED` | The service accepted the request and has yet to claim it. Queue time does not count against the Run's execution budget. |
| `RUNNING` | The service claimed the request. Stage progress can lag behind execution. |
| `FINISHED` | The executor finished and returned packaged evidence. Check the Run outcome to learn whether the candidate was verified. |
| `FAILED` | The executor raised an error. Inspect the retained Run records for the failure reason. |
| `INTERRUPTED` | Service ownership was lost after the request was claimed. A Run can still have complete evidence if the service stopped after packaging. |

For scripts, `harborist run SOURCE --json` returns a delivery record in
background mode. Use `harborist status RUN_ID --wait --json` and inspect
`run.outcome` and `run.failure_reason` after delivery ends. Saved foreground
Runs can appear in history without a service delivery state.

## Troubleshoot startup and execution

| Symptom | What to do |
| --- | --- |
| Submission reports that the service is unavailable | Start the service and submit the printed Run UUID if capture already succeeded. |
| Service startup reports a Unix socket path error | Choose a shorter local `--control-dir` and use it consistently across the service, CLI, and browser. |
| The service cannot locate Codex or use its credentials | Check the provider in **Integrations → Codex**. Restart the service from the environment with the expected CLI and credentials. |
| A Run was interrupted | Check its saved outcome and evidence. The service preserves the claim on restart. If recovery is appropriate, follow [Rework and recovery](usage.md#rework-and-recovery). |

The default service log is `~/.harborist/control/service.log`. See [Storage
and recovery](storage-and-recovery.md) for the queue, logs, and Run data paths.

## Upgrade an existing installation

After updating Harborist, restart the service after it drains active work. New
configuration uses `harborist.yaml` and `harborist.settings.yaml`. Harborist
still reads the previous filenames when the corresponding current file is
absent. It continues using an existing `~/.shipyard` data directory if
`~/.harborist` has yet to be created. Existing candidate refs retain their
original namespace.
