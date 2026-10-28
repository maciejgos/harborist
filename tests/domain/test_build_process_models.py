import pytest
from pydantic import ValidationError

from shipyard.domain.build_process import BuildProcessReport


def test_process_report_preserves_reported_failures_without_granting_success() -> None:
    report = BuildProcessReport.model_validate(
        {
            "checks": [
                {
                    "phase": "red",
                    "command": "pytest -k version",
                    "returncode": 1,
                    "output": "FAILED: missing --version",
                },
                {
                    "phase": "green",
                    "command": "pytest -k version",
                    "returncode": 2,
                    "output": "Collection failed; implementation not verified",
                },
            ],
            "limitations": "Commands and order are agent-reported, not independently observed.",
        }
    )
    assert report.checks[1].returncode == 2
    assert BuildProcessReport.model_validate_json(report.model_dump_json()) == report
    with pytest.raises(ValidationError):
        BuildProcessReport.model_validate(
            {
                "checks": [
                    {
                        "phase": "red",
                        "command": "pytest",
                        "returncode": 1,
                        "output": "x" * 8193,
                    }
                ],
                "limitations": "Unknown",
            }
        )
