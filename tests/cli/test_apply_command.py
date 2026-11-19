import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harborist.cli import app
from harborist.domain import RunContract
from tests.application.test_apply import packaged as packaged  # noqa: PLC0414
from tests.cli.conftest import strip_ansi


def test_apply_cli(packaged: tuple[Path, Path, RunContract, str]) -> None:
    root, repo, contract, candidate = packaged
    args = [
        "apply",
        str(contract.run_id),
        "--branch",
        "main",
        "--repo",
        str(repo),
        "--runs-dir",
        str(root),
    ]
    runner = CliRunner()
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Applied" in result.stdout
    assert candidate in result.stdout
    assert "Receipt:" in result.stdout
    repeated = runner.invoke(app, args)
    assert repeated.exit_code == 0
    assert "Already applied" in repeated.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["apply", "bad", "--branch", "main"],
        ["apply", "00000000-0000-4000-8000-000000000001"],
    ],
)
def test_invalid_args(args: list[str]) -> None:
    assert CliRunner().invoke(app, args).exit_code != 0


def test_apply_help() -> None:
    result = CliRunner().invoke(app, ["apply", "--help"])
    assert result.exit_code == 0
    text = strip_ansi(result.stdout)
    for option in ("--repo", "--runs-dir", "--branch"):
        assert option in text


def test_guidance_quotes_paths(tmp_path: Path) -> None:
    from uuid import uuid4

    from harborist.cli.run_summary import application_guidance

    run_id = uuid4()
    repo = tmp_path / "repo with spaces"
    root = tmp_path / "custom storage"
    lines = application_guidance(run_id=run_id, repository=repo, root=root)
    assert "Verified; awaiting application" in lines[0]
    command = shlex.split(lines[-1])
    assert command == [
        "harborist",
        "apply",
        str(run_id),
        "--branch",
        "REPLACE_WITH_LOCAL_BRANCH",
        "--repo",
        str(repo.resolve()),
        "--runs-dir",
        str(root.resolve()),
    ]


def test_saved_apply_context(
    tmp_path: Path, frozen_contract: RunContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harborist.application.context import ExecutionContext
    from harborist.application.execution import execute_run
    from tests.application.test_run_execution import FakeAgent, capture

    store, repository, contract = capture(tmp_path, frozen_contract)
    root = store.directory(contract.run_id).parent.resolve()
    repo = repository.checkout_root()
    ExecutionContext(
        version=1, run_id=contract.run_id, repository=repo, runs_root=root
    ).save()
    evidence = execute_run(
        store=store,
        run_id=contract.run_id,
        repository=repository,
        workspace=tmp_path / "work",
        agent=FakeAgent(),
    )
    assert evidence.candidate is not None
    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    result = CliRunner().invoke(
        app,
        ["apply", str(contract.run_id), "--branch", "main", "--runs-dir", str(root)],
    )
    assert result.exit_code == 0, result.output
    assert evidence.candidate.candidate_sha in result.stdout
