# Harborist documentation

Harborist runs software engineering requests against a local Git repository. It
captures the request, builds a candidate commit, runs your mandatory checks, and
reviews that exact commit against the acceptance criteria. You decide when to
apply a verified candidate locally or publish it to GitHub.

In the container deployment, the worker and browser workspace run in local
Docker containers. With the Docker Sandboxes policy selected, the worker
executes agent stages and mandatory checks in separate, fresh VMs on the Mac.

## Start here

Follow [Run Harborist with Docker](quickstart.md) to start the containers,
select the sandbox policy, and inspect your first Run.

## Guides

| I want to… | Read |
| --- | --- |
| Capture a request, inspect the result, or deliver a candidate | [Run and deliver changes](usage.md) |
| Configure a repository, Codex, or Docker Sandboxes | [Configure Harborist](configuration.md) |
| Start, stop, or troubleshoot the local worker | [Operate the local service](background-control-plane.md) |
| Understand what Harborist verifies | [Workflow and verification](methodology.md) |
| Locate evidence or recover from an interruption | [Storage and recovery](storage-and-recovery.md) |
| Look up a command or option | [CLI reference](../COMMANDS.md) |

## Develop Harborist

For implementation details, see the [architecture](../ARCHITECTURE.md),
[developer reference](developer-reference.md), and [contribution
instructions](../AGENTS.md). Release and planning records are available in
the [changelog](../CHANGELOG.md) and [roadmap](../ROADMAP.md).
