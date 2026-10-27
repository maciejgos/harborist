from pathlib import Path

from shipyard.domain import VerificationCheck, VerificationConfig
from shipyard.verification.runner import run_checks


def test_collects_all_checks_after_failure(tmp_path: Path) -> None:
    config = VerificationConfig(
        version=1,
        checks=(
            VerificationCheck(id="bad", command="printf broken >&2; exit 3"),
            VerificationCheck(id="good", command="printf done"),
        ),
    )
    result = run_checks(
        config=config, workspace=tmp_path, logs_dir=tmp_path / "logs", timeout_seconds=2
    )
    assert not result.passed
    assert [check.returncode for check in result.checks] == [3, 0]
    assert Path(result.checks[0].stderr_path).read_text() == "broken"
    assert Path(result.checks[1].stdout_path).read_text() == "done"


def test_timeout_continues_collection(tmp_path: Path) -> None:
    config = VerificationConfig(
        version=1,
        checks=(
            VerificationCheck(id="slow", command="sleep 10"),
            VerificationCheck(id="next", command="true"),
        ),
    )
    result = run_checks(
        config=config,
        workspace=tmp_path,
        logs_dir=tmp_path / "logs",
        timeout_seconds=0.05,
    )
    assert result.checks[0].timed_out
    assert result.checks[1].returncode == 0
    assert not result.passed


def test_logs_are_bounded_and_truncation_is_explicit(tmp_path: Path) -> None:
    config = VerificationConfig(
        version=1,
        checks=(VerificationCheck(id="noisy", command="yes x | head -c 100000"),),
    )
    result = run_checks(
        config=config,
        workspace=tmp_path,
        logs_dir=tmp_path / "logs",
        timeout_seconds=2,
        max_log_bytes=100,
    )
    assert result.passed
    assert result.checks[0].stdout_truncated
    assert not result.checks[0].stderr_truncated
    assert len(Path(result.checks[0].stdout_path).read_bytes()) == 100


def test_total_deadline_records_unstarted_checks(tmp_path: Path) -> None:
    config = VerificationConfig(
        version=1,
        checks=(
            VerificationCheck(id="slow", command="sleep 10"),
            VerificationCheck(id="later", command="touch must-not-exist"),
        ),
    )
    result = run_checks(
        config=config,
        workspace=tmp_path,
        logs_dir=tmp_path / "logs",
        timeout_seconds=2,
        total_timeout_seconds=0.05,
    )
    assert all(check.timed_out for check in result.checks)
    assert not (tmp_path / "must-not-exist").exists()
