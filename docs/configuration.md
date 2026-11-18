# Configuration

[Documentation index](README.md) · [Architecture](../ARCHITECTURE.md)

## Frozen verification configuration

Target repositories commit a narrow `shipyard.yaml`:

```yaml
version: 1
checks:
  - id: tests
    command: pytest
```

Every listed check is mandatory. At least one check is required; IDs must be
unique and commands nonblank. Unknown fields, unsupported versions, duplicate YAML
keys, and unsafe object tags are rejected. Command strings retain their exact text.

```python
from shipyard.verification import load_verification_config

base_sha = repository.resolve_base()
verification = load_verification_config(repository=repository, base_sha=base_sha)
```

The loader reads the root `shipyard.yaml` from that exact commit, ignoring index
and working-tree edits. Its immutable snapshot retains validated settings, base
SHA, and a SHA-256 of the original file bytes. Git replacement refs cannot substitute
other content for committed-file reads. YAML source text is not retained.

`VerificationConfigError` reports read/parsing/validation failures with causes.
This loader does not execute checks or change Run outcomes. `execute_test` performs trusted TEST. See the [verification configuration specification](../spec/010-verification-config/spec.md).

## Operator execution settings

The CLI selects exactly `<resolved-target-checkout-root>/shipyard.settings.yaml`
when `--settings` is omitted. `--repo` selects the target (default: `.`); Git
resolves its root even from a subdirectory. Caller configuration cannot override
another target repository. Explicit `--settings PATH` takes precedence, supports
files outside the target, and resolves relative paths from the invocation
directory. Playbook and skill paths resolve beside the selected settings file.
There is no recursive search, global/home fallback, merging, or file creation.

Missing, unreadable, or invalid selected settings fail before Run creation; the
diagnostic names the path and instructs you to supply `--settings PATH`. An invalid
explicit override never falls back. Existing Runs use their frozen settings and
methodology and never reload or rediscover these files. Execution settings are
local intake inputs independent of `--ref`; mandatory checks remain in
`shipyard.yaml` at the frozen base SHA and cannot be overridden by settings.
GitHub examples require an installed, authenticated `gh` with issue access.

`load_execution_settings(path=Path("operator.yaml"))` captures a version 1 YAML
file with `playbook` and `skills` source records (`name`, `version`, `path`), a
complete `agent_profile` (`name`, `version`, `provider`, `model`, `arguments`) and
`sandbox_policy: trusted-local`. Asset paths resolve beside the settings file.
Actual UTF-8 content and SHA-256 digests are frozen, so future file edits have no
live link to a snapshot. The agent model is an explicit operator choice.

The local adapter accepts `provider: codex` and a model identifier. Use
`arguments: []` for the Codex default reasoning effort, or use the pair
`['-c', 'model_reasoning_effort="high"']`. Supported effort values are
`minimal`, `low`, `medium`, `high`, and `xhigh`. See
[local Codex setup](usage.md#set-up-local-codex) for diagnostics and editing.

Budget is excluded from YAML. Shipyard defaults to 1800 total seconds with 300
reserved for verification; callers may pass an explicit `ExecutionBudget` to the
loader. The target repository cannot set it. Unknown fields, duplicate YAML keys,
unsupported versions, invalid records and unreadable assets fail with
`SettingsError`. See [settings specification](../spec/013-execution-settings/spec.md).


## Budget accounting

A Run has one frozen budget. `BudgetClock` uses monotonic elapsed time from
execution admission; DESIGN/PLAN/BUILD cannot consume the verification reserve.
TEST/REVIEW share the remaining total. Stage timing survives ordinary failures;
PACKAGE records its timing separately and does not consume execution allowance.
Remaining subsecond allowance cannot admit a native-agent call. UTC wall-clock
timestamps describe events; elapsed monotonic time controls deadlines.
