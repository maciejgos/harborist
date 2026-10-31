# Implementation plan

Use an OS advisory ownership lock and private Unix HTTP socket. The service main thread executes serially; a separate HTTP thread admits requests under a shared gate. Graceful stop closes admission and drains execution. Startup marks old claims INTERRUPTED. Add detached start, foreground serve, health and stop CLI commands; test ownership, permissions, malformed requests and draining.

Validation: focused red → green tests, then full pytest, Ruff and Pyright.
