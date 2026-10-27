"""Native-stage integration: real subprocesses and Git, synthetic provider."""

from pathlib import Path

from shipyard.agents.codex import CodexAgent
from shipyard.application.stages import StageExecution, execute_stage
from shipyard.application.verification import execute_test
from shipyard.domain import RunContract
from shipyard.domain.attempt import Attempt
from shipyard.domain.playbook_execution import StepOutcome
from shipyard.domain.stage_result import AgentStage
from shipyard.git import GitRepository
from shipyard.verification.config import load_verification_config
from tests.agents.test_codex import fake
from tests.git_helpers import git, init_repository


def test_all_stages_use_independent_codex_processes(
    tmp_path: Path,
    frozen_contract: RunContract,
) -> None:
    executable = fake(
        tmp_path,
        """import json, pathlib, sys
args = sys.argv[1:]
assert args[0] == 'exec'
assert '--ephemeral' in args and '--ignore-user-config' in args
prompt = sys.stdin.read()
request = json.loads(prompt[prompt.index('{'):])
stage = request['stage']
assert request['timeout_seconds'] == 30
assert request['guidance']['stage'] == stage
sandbox = args[args.index('--sandbox') + 1]
assert sandbox == ('workspace-write' if stage == 'build' else 'read-only')
schema = json.loads(pathlib.Path(args[args.index('--output-schema') + 1]).read_text())
assert schema['properties']['result']['properties']['stage']['const'] == stage
inputs = {item['name']: item['content'] for item in request['inputs']}
if stage in ('plan', 'build', 'review'):
    assert inputs['spec.md'] == '# Spec\\r\\nAC-001: Implement requested change.\\r\\n'
if stage == 'build':
    assert inputs['plan.md'] == '# Plan'
    pathlib.Path(request['workspace'], 'implemented.txt').write_text('done')
result = {'stage': stage, 'status': 'ready'}
if stage == 'review':
    assert pathlib.Path(request['workspace'], 'implemented.txt').read_text() == 'done'
    assert 'test-evidence.json' in inputs
    result.update(candidate=request['candidate'], criteria=[{'criterion_id': 'AC-001', 'status': 'pass'}])
artifacts = {'design': '# Spec\\r\\nAC-001: Implement requested change.\\r\\n',
             'plan': '# Plan', 'build': None, 'review': '# Review'}
pathlib.Path(args[args.index('--output-last-message') + 1]).write_text(json.dumps({
    'result': result, 'artifact': artifacts[stage],
    'plan_update': '# Revised plan' if stage == 'build' else None,
}))
""",
    )
    repository = tmp_path / "repository"
    init_repository(repository)
    (repository / "shipyard.yaml").write_text(
        "version: 1\nchecks:\n  - id: test\n    command: test -f implemented.txt\n"
    )
    git(repository, "add", ".")
    git(repository, "commit", "-m", "base")
    repo = GitRepository(path=repository)
    base = repo.resolve_base()
    frozen_contract = RunContract(
        run_id=frozen_contract.run_id,
        intent=frozen_contract.intent,
        base_sha=base,
        execution=frozen_contract.execution,
        verification=load_verification_config(repository=repo, base_sha=base),
    )
    attempt = Attempt.create(
        frozen_contract.run_id, git(repository, "rev-parse", "HEAD")
    )
    isolated = GitRepository(path=repository).create_workspace(
        attempt=attempt, path=tmp_path / "workspace"
    )
    workspace = isolated.path
    upstream: dict[str, Path] = {}
    for stage in (AgentStage.DESIGN, AgentStage.PLAN, AgentStage.BUILD):
        directory = tmp_path / stage.value
        result = execute_stage(
            contract=RunContract.model_validate_json(frozen_contract.model_dump_json()),
            attempt=attempt,
            stage=stage,
            workspace=workspace,
            upstream=upstream,
            output_dir=directory,
            agent=CodexAgent(executable=str(executable)),
            remaining_seconds=30,
        )
        assert (
            StageExecution.model_validate_json(
                (directory / "manifest.json").read_bytes()
            )
            == result
        )
        if stage == AgentStage.DESIGN:
            upstream["spec.md"] = directory / "spec.md"
        if stage == AgentStage.PLAN:
            upstream["plan.md"] = directory / "plan.md"
    candidate = isolated.publish_candidate()
    assert (
        git(repository, "rev-parse", isolated.candidate_ref) == candidate.candidate_sha
    )
    assert git(repository, "rev-parse", "HEAD") == attempt.start_sha
    test_result = execute_test(
        contract=frozen_contract,
        attempt=attempt,
        candidate=candidate,
        workspace=workspace,
        output_dir=tmp_path / "test",
        check_timeout_seconds=2,
    )
    evidence = tmp_path / "test" / "manifest.json"
    receipt = test_result.receipt
    assert receipt.outcome == StepOutcome.SUCCEEDED
    result = execute_stage(
        contract=RunContract.model_validate_json(frozen_contract.model_dump_json()),
        attempt=attempt,
        stage=AgentStage.REVIEW,
        workspace=workspace,
        upstream={"spec.md": upstream["spec.md"], "test-evidence.json": evidence},
        output_dir=tmp_path / "review",
        agent=CodexAgent(executable=str(executable)),
        remaining_seconds=30,
        candidate=candidate,
        test_receipt=receipt,
    )
    assert result.output.result.stage == AgentStage.REVIEW
    assert result.candidate == candidate
    assert git(workspace, "status", "--porcelain") == ""
