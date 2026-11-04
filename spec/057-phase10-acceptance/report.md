# Phase 10 acceptance — 2026-10-31

> Status update — 2026-11-04: Phase 9 is completed by owner decision. The owner accepted the retained PoC evidence and waived the matched direct-Codex comparison as an exit requirement. Outstanding Phase 9 statements below describe the historical assessment.

All eight slices are implemented, with separate specifications and commits.

## Closure — 2026-11-04

**Phase 10: Completed.** The original eight slices and browser/history follow-ups
(specifications 058–060) satisfy the local background control-plane scope.

Closure validation on the current checkout:

- Full `uv run pytest -q`, with local socket/process access enabled: **894 passed**, 78.11 seconds. The seven permission-related failures from the restricted run did not recur.
- Ruff: clean. Pyright: zero errors/warnings. `git diff --check`: clean.
- README, architecture, service guide and roadmap now record completion.
- AGENTS.md now describes the local single-user MVP, synchronous execution core, serial background service, read-only browser monitor and filesystem persistence. Exact-revision verification rules remain in force.

This closure changes documentation only; it adds no execution behavior. Existing
browser acceptance is recorded in specifications 058–060 and was not rerun for
this documentation update. Live paid-agent calls, recovery/rework and GitHub
publication are not required for Phase 10 closure. Phase 11 is next.


| Slice | Acceptance evidence |
| --- | --- |
| 10.1 Service contract | [Architecture](../../ARCHITECTURE.md), [service contract and operating guide](../../docs/background-control-plane.md); owner authorization recorded without declaring Phase 9 complete. |
| 10.2 Durable queue | [Queue tests](../../tests/control/test_queue.py): idempotent submission, conflicting locators, exclusive claim, restart interruption and corrupt records. |
| 10.3 Background executor | [Worker tests](../../tests/control/test_worker.py): real Git, mandatory checks, independent review and exact-SHA VERIFIED packaging; preflight failure retained without retry. |
| 10.4 Service lifecycle | [Service tests](../../tests/control/test_service.py): exclusive owner, private socket, malformed JSON, admission closure, active drain and pending-work retention. [Process tests](../../tests/control/test_detached.py) exercise detached start/stop. |
| 10.5 CLI client | [Submission tests](../../tests/cli/test_background.py): default saved-Run and source submission, frozen context, connection diagnostics and retained captures. Existing execution tests explicitly select foreground compatibility. |
| 10.6 Monitoring | [CLI monitoring tests](../../tests/cli/test_monitoring.py): list, terminal polling, human outcome/evidence summary and JSON. All requests are read-only. |
| 10.7 Web read model | [Projection tests](../../tests/control/test_read_model.py): delivery versus Run state, Attempt identity, package references, unavailable lifecycle and invalid routes. |
| 10.8 End-to-end acceptance | [Detached-process tests](../../tests/control/test_detached.py): submitting CLI exits while execution remains active; real canonical execution then packages VERIFIED evidence. Duplicate submission does not start another execution. Forced service death produces INTERRUPTED on restart without resuming or packaging fabricated evidence. |

## Validation

Full repository validation uses `uv run pytest`, `uv run ruff check .` and
`uv run pyright`. Local socket/process tests require execution permission to
create a Unix socket; the restricted test environment blocks socket binding.
The validation run used a temporary uv cache, without changing project settings.

Final results: **876 tests passed** (86.73 seconds), Ruff clean, Pyright zero
errors/warnings. `git diff --check` also passed.

## Limits and deferred work

- Integration tests replace native-agent responses; no live paid agent call is part of this acceptance.
- The service is local and serial, using filesystem persistence and an owner-only Unix HTTP socket. No browser frontend, TCP service, database or distributed worker is introduced.
- Graceful stop drains active work. Forced termination can leave external subprocesses alive; restart never launches replacements for claimed work. Recovery and rework remain Phase 11.
- Queue snapshots are atomic/fsynced, but Git, lifecycle journals and PACKAGE are not a single transaction. Power-loss behavior is not certified.
- Package availability indicates file presence; evidence integrity remains independently checked by explicit apply.
- Phase 9's matched direct-Codex comparison and explicit trust evaluation remain outstanding.

## Browser UI follow-up

This report covered the initial JSON read model. Owner clarification required a
visible browser monitor; specification 058 and its report record that correction.
The earlier statement excluding a browser frontend is superseded by that work.
