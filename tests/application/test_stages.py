import json
from collections.abc import Callable
from pathlib import Path

import pytest

from harborist.agents.base import AgentExecutionError, AgentRequest, AgentResponse
from harborist.application.stages import execute_stage
from harborist.domain import RunContract
from harborist.domain.artifact import ArtifactStage
from harborist.domain.attempt import Attempt
from harborist.domain.playbook_execution import StageReceipt, StepOutcome
from harborist.domain.stage_result import AgentStage, InvalidStageOutput
from tests.application.test_review import capture
from tests.git_helpers import git, init_repository


class FakeAgent:
    def __init__(
        self, action: Callable[[AgentRequest], AgentResponse] | None = None
    ) -> None:
        self.requests: list[AgentRequest] = []
        self.action = action

    def execute(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        if self.action:
            return self.action(request)
        result: dict[str, object] = {"stage": request.stage.value, "status": "ready"}
        if request.candidate:
            result.update(
                candidate=request.candidate.model_dump(mode="json"),
                criteria=[{"criterion_id": "AC-001", "status": "pass"}],
            )
        return AgentResponse(
            returncode=0,
            output=json.dumps(
                {
                    "result": result,
                    "artifact": {
                        AgentStage.DESIGN: "# Artifact\r\nAC-001: Required behavior\r\n",
                        AgentStage.PLAN: "# Artifact\r\n",
                        AgentStage.BUILD: None,
                        AgentStage.REVIEW: "# Artifact\r\n",
                    }[request.stage],
                    "plan_update": "# Revised plan"
                    if request.stage == AgentStage.BUILD
                    else None,
                }
            ),
        )


def test_independent_durable_chain(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(frozen_contract.model_dump_json())
    attempt = Attempt.create(frozen_contract.run_id, frozen_contract.base_sha)
    upstream: dict[str, Path] = {}
    for stage in (AgentStage.DESIGN, AgentStage.PLAN, AgentStage.BUILD):
        agent = FakeAgent()
        result = execute_stage(
            contract=RunContract.model_validate_json(contract_path.read_bytes()),
            attempt=Attempt.model_validate_json(attempt.model_dump_json()),
            stage=stage,
            workspace=workspace,
            upstream=upstream,
            output_dir=tmp_path / stage.value,
            agent=agent,
            remaining_seconds=30,
        )
        assert result.output.result.stage == stage
        assert len(agent.requests) == 1
        directory = tmp_path / stage.value
        assert (directory / "manifest.json").is_file()
        if stage == AgentStage.DESIGN:
            upstream["spec.md"] = directory / "spec.md"
        elif stage == AgentStage.PLAN:
            upstream["plan.md"] = directory / "plan.md"
    assert (
        upstream["spec.md"].read_bytes()
        == b"# Artifact\r\nAC-001: Required behavior\r\n"
    )
    assert upstream["plan.md"].read_bytes() == b"# Artifact\r\n"
    assert (tmp_path / "build" / "plan.md").read_text() == "# Revised plan"
    with pytest.raises(FileExistsError):
        execute_stage(
            contract=frozen_contract,
            attempt=attempt,
            stage=AgentStage.DESIGN,
            workspace=workspace,
            upstream={},
            output_dir=tmp_path / "design",
            agent=FakeAgent(),
            remaining_seconds=30,
        )


def test_failures_leave_no_success_manifest(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    attempt = Attempt.create(frozen_contract.run_id, frozen_contract.base_sha)
    for name, response, error in (
        ("process", AgentResponse(returncode=1, output="{}"), AgentExecutionError),
        ("json", AgentResponse(returncode=0, output="prose"), InvalidStageOutput),
    ):
        with pytest.raises(error):
            execute_stage(
                contract=frozen_contract,
                attempt=attempt,
                stage=AgentStage.DESIGN,
                workspace=workspace,
                upstream={},
                output_dir=tmp_path / name,
                agent=FakeAgent(lambda _, response=response: response),
                remaining_seconds=30,
            )
        assert not (tmp_path / name / "manifest.json").exists()


def test_build_cannot_rewrite_spec(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    spec = workspace / "spec.md"
    spec.write_text("# Contract")
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan")

    def mutate(request: AgentRequest) -> AgentResponse:
        spec.write_text("# Weakened")
        return FakeAgent().execute(request)

    with pytest.raises(InvalidStageOutput, match="Upstream"):
        execute_stage(
            contract=frozen_contract,
            attempt=Attempt.create(frozen_contract.run_id, frozen_contract.base_sha),
            stage=AgentStage.BUILD,
            workspace=workspace,
            upstream={"spec.md": spec, "plan.md": plan},
            output_dir=tmp_path / "output",
            agent=FakeAgent(mutate),
            remaining_seconds=30,
        )
    assert not (tmp_path / "output" / "manifest.json").exists()


def test_review_requires_successful_exact_test_and_clean_checkout(
    tmp_path: Path,
    frozen_contract: RunContract,
) -> None:
    workspace = tmp_path / "workspace"
    init_repository(workspace)
    git(workspace, "commit", "--allow-empty", "-m", "candidate")
    sha = git(workspace, "rev-parse", "HEAD")
    attempt = Attempt.create(frozen_contract.run_id, sha)
    candidate = attempt.create_candidate(sha)
    spec = tmp_path / "spec.md"
    spec.write_text("AC-001: Required")
    evidence = tmp_path / "test-evidence.json"
    evidence.write_text(
        capture(frozen_contract, attempt, candidate=candidate).model_dump_json()
    )

    def run(name: str, receipt: StageReceipt) -> None:
        execute_stage(
            contract=frozen_contract,
            attempt=attempt,
            stage=AgentStage.REVIEW,
            workspace=workspace,
            upstream={"spec.md": spec, "test-evidence.json": evidence},
            output_dir=tmp_path / name,
            agent=FakeAgent(),
            remaining_seconds=30,
            candidate=candidate,
            test_receipt=receipt,
        )

    failed = StageReceipt(
        stage=ArtifactStage.TEST, outcome=StepOutcome.TEST_FAILED, candidate=candidate
    )
    with pytest.raises(ValueError, match="TEST"):
        run("failed-test", failed)
    passed = StageReceipt(
        stage=ArtifactStage.TEST, outcome=StepOutcome.SUCCEEDED, candidate=candidate
    )
    run("review", passed)
    (workspace / "dirty").write_text("dirty")
    with pytest.raises(ValueError, match="clean"):
        run("dirty", passed)


def test_review_rejects_workspace_mutation_and_foreign_test(
    tmp_path: Path,
    frozen_contract: RunContract,
) -> None:
    workspace = tmp_path / "workspace"
    init_repository(workspace)
    git(workspace, "commit", "--allow-empty", "-m", "candidate")
    sha = git(workspace, "rev-parse", "HEAD")
    attempt = Attempt.create(frozen_contract.run_id, sha)
    candidate = attempt.create_candidate(sha)
    spec = tmp_path / "spec.md"
    spec.write_text("AC-001: Required")
    evidence = tmp_path / "test-evidence.json"
    evidence.write_text(
        capture(frozen_contract, attempt, candidate=candidate).model_dump_json()
    )

    def mutate(request: AgentRequest) -> AgentResponse:
        (workspace / "unexpected").write_text("modified")
        return FakeAgent().execute(request)

    passed = StageReceipt(
        stage=ArtifactStage.TEST, outcome=StepOutcome.SUCCEEDED, candidate=candidate
    )
    with pytest.raises(ValueError, match="clean"):
        execute_stage(
            contract=frozen_contract,
            attempt=attempt,
            stage=AgentStage.REVIEW,
            workspace=workspace,
            upstream={"spec.md": spec, "test-evidence.json": evidence},
            output_dir=tmp_path / "mutated",
            agent=FakeAgent(mutate),
            remaining_seconds=30,
            candidate=candidate,
            test_receipt=passed,
        )
    assert not (tmp_path / "mutated" / "manifest.json").exists()
    foreign = passed.model_copy(
        update={"candidate": attempt.create_candidate("b" * 40)}
    )
    with pytest.raises(ValueError, match="TEST"):
        execute_stage(
            contract=frozen_contract,
            attempt=attempt,
            stage=AgentStage.REVIEW,
            workspace=workspace,
            upstream={"spec.md": spec, "test-evidence.json": evidence},
            output_dir=tmp_path / "foreign",
            agent=FakeAgent(),
            remaining_seconds=30,
            candidate=candidate,
            test_receipt=foreign,
        )


@pytest.mark.parametrize(
    "defect", ["empty-evidence", "incomplete-review", "unknown-criterion"]
)
def test_invalid_review_has_no_success_capture(
    tmp_path: Path, frozen_contract: RunContract, defect: str
) -> None:
    workspace = tmp_path / "workspace"
    init_repository(workspace)
    git(workspace, "commit", "--allow-empty", "-m", "candidate")
    sha = git(workspace, "rev-parse", "HEAD")
    attempt = Attempt.create(frozen_contract.run_id, sha)
    candidate = attempt.create_candidate(sha)
    spec = tmp_path / "spec.md"
    spec.write_text("AC-001: Required\nAC-002: Also required")
    test = capture(frozen_contract, attempt, candidate=candidate)
    evidence = tmp_path / "test.json"
    evidence.write_text("{}" if defect == "empty-evidence" else test.model_dump_json())

    def respond(request: AgentRequest) -> AgentResponse:
        response = FakeAgent().execute(request)
        if defect == "unknown-criterion":
            return AgentResponse(
                returncode=0, output=response.output.replace("AC-001", "AC-999")
            )
        return response

    agent = FakeAgent(respond)
    with pytest.raises(ValueError):
        execute_stage(
            contract=frozen_contract,
            attempt=attempt,
            candidate=candidate,
            stage=AgentStage.REVIEW,
            workspace=workspace,
            upstream={"spec.md": spec, "test-evidence.json": evidence},
            output_dir=tmp_path / "review",
            agent=agent,
            remaining_seconds=30,
            test_receipt=test.receipt,
        )
    assert not (tmp_path / "review" / "manifest.json").exists()
    assert len(agent.requests) == (0 if defect == "empty-evidence" else 1)


@pytest.mark.parametrize(
    "body",
    [
        "raise SystemExit(7)",
        "pass",  # No final message.
        "import pathlib; pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1]).write_bytes(b'x' * (4 * 1024 * 1024 + 1))",
        "import pathlib; pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1]).write_bytes(bytes([255]))",
    ],
    ids=["nonzero", "missing-final", "oversized-final", "invalid-utf8-final"],
)
def test_failed_native_process_retains_bounded_diagnostics(
    tmp_path: Path,
    frozen_contract: RunContract,
    body: str,
) -> None:
    from harborist.agents.codex import CodexAgent
    from tests.agents.test_codex import fake

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = fake(
        tmp_path,
        "import sys; sys.stderr.write('x' * 100000); sys.stderr.flush()\n" + body,
    )
    directory = tmp_path / "design"
    with pytest.raises(AgentExecutionError):
        execute_stage(
            contract=frozen_contract,
            attempt=Attempt.create(frozen_contract.run_id, frozen_contract.base_sha),
            stage=AgentStage.DESIGN,
            workspace=workspace,
            upstream={},
            output_dir=directory,
            agent=CodexAgent(executable=str(executable)),
            remaining_seconds=2,
        )
    assert len((directory / "stderr.log").read_bytes()) == 65536
    assert json.loads((directory / "invocation.json").read_text())["stderr_truncated"]
    assert not (directory / "manifest.json").exists()


def test_review_rejects_foreign_process_report_before_invocation(
    tmp_path: Path, frozen_contract: RunContract
) -> None:
    from uuid import uuid4

    from harborist.domain.build_process import BuildProcessEvidence, BuildProcessReport

    workspace = tmp_path / "workspace"
    init_repository(workspace)
    git(workspace, "commit", "--allow-empty", "-m", "candidate")
    sha = git(workspace, "rev-parse", "HEAD")
    attempt = Attempt.create(frozen_contract.run_id, sha)
    candidate = attempt.create_candidate(sha)
    spec = tmp_path / "spec.md"
    spec.write_text("AC-001: Required")
    test = capture(frozen_contract, attempt, candidate=candidate)
    evidence = tmp_path / "test.json"
    evidence.write_text(test.model_dump_json())
    process = tmp_path / "build-process.json"
    process.write_text(
        BuildProcessEvidence(
            run_id=frozen_contract.run_id,
            attempt_id=uuid4(),
            report=BuildProcessReport(checks=(), limitations="No executions reported"),
        ).model_dump_json()
    )
    agent = FakeAgent()
    with pytest.raises(ValueError, match="process evidence"):
        execute_stage(
            contract=frozen_contract,
            attempt=attempt,
            candidate=candidate,
            stage=AgentStage.REVIEW,
            workspace=workspace,
            upstream={
                "spec.md": spec,
                "test-evidence.json": evidence,
                "build-process.json": process,
            },
            output_dir=tmp_path / "review",
            agent=agent,
            remaining_seconds=30,
            test_receipt=test.receipt,
        )
    assert not agent.requests
    assert not (tmp_path / "review").exists()
