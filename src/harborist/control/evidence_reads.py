"""Bounded, Attempt-scoped browser evidence reads."""

import re
from pathlib import Path

from harborist.application.verification import TestExecution
from harborist.control.read_model import RunView, project
from harborist.domain import RunLifecycle
from harborist.persistence import FileRunStore

ARTIFACT = r"(?:report\.md|evidence\.json|spec\.md|test-\d{4}-(?:stdout|stderr))"
ATTEMPTS = re.compile(
    rf"/runs/([^/]+)/attempts(?:/(\d{{1,6}})(?:/artifacts/({ARTIFACT}))?)?"
)


def read_text(directory: Path, relative: str) -> str:
    artifact = directory / relative
    if any(path.is_symlink() for path in (directory, artifact, *artifact.parents)):
        raise ValueError("Artifact must be a regular file inside its Attempt")
    if not artifact.is_file():
        raise ValueError("Artifact is unavailable")
    with artifact.open("rb") as source:
        content = source.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Artifact exceeds the 2 MiB viewing limit")
    return content.decode("utf-8", errors="replace")


def attempt_evidence(
    record: RunView, number: str | None, name: str | None
) -> dict[str, object]:
    run_id = record.submission.run_id
    store = FileRunStore(root=record.submission.runs_root)
    numbers = store.numbers(run_id)
    if number is None:
        return {"attempts": numbers}
    index = int(number)
    if index not in numbers:
        raise ValueError("Unknown Attempt")
    pinned = store.pinned(run_id, index)
    directory = pinned.directory(run_id)
    view = (
        record
        if index == record.attempt_number
        else project(
            RunView(submission=record.submission, source=record.source), number=index
        )
    )
    if name is not None:
        if view.run is None or view.run.lifecycle not in (
            RunLifecycle.COMPLETED,
            RunLifecycle.FAILED,
            RunLifecycle.CANCELLED,
        ):
            raise ValueError("Terminal artifact is not available yet")
        match = re.fullmatch(r"test-(\d{4})-(stdout|stderr)", name)
        if match:
            if "test" not in view.stages or "test" in view.stage_errors:
                raise ValueError("Validated TEST evidence is unavailable")
            relative = f"test/logs/{match[1]}.{match[2]}.log"
        elif name == "spec.md":
            relative = (
                "frozen-spec.md"
                if (directory / "frozen-spec.md").exists()
                else "design/spec.md"
            )
        else:
            relative = name
        return {"name": name, "content": read_text(directory, relative)}

    result = view.model_dump(mode="json")
    result["has_specification"] = any(
        (directory / name).is_file() for name in ("frozen-spec.md", "design/spec.md")
    )
    if (
        "test" in view.stages
        and "test" not in view.stage_errors
        and view.run
        and view.run.lifecycle != RunLifecycle.RUNNING
    ):
        try:
            test = TestExecution.model_validate_json(
                read_text(directory, "test/manifest.json")
            )
            result["checks"] = [
                {
                    **check.model_dump(exclude={"stdout_path", "stderr_path"}),
                    "passed": check.passed,
                }
                for check in test.collection.checks
            ]
        except (OSError, ValueError) as error:
            result["checks_error"] = str(error)
    return result
