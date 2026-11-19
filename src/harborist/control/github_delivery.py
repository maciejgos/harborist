"""Browser GitHub commands and saved collaboration evidence."""

import subprocess
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from harborist.application import collaboration, publication
from harborist.control.read_model import RunView
from harborist.domain.revision import GitCommitSha


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: GitCommitSha
    expected_attempt: UUID
    destination: str = Field(min_length=1, max_length=256)
    base: str = Field(min_length=1, max_length=256)
    expect_head: GitCommitSha | None = None


def observation_response(
    observation: collaboration.Observation, path: Path
) -> dict[str, object]:
    return {
        "observation": observation.model_dump(mode="json"),
        "observation_path": str(path),
    }


def read_delivery(record: RunView) -> dict[str, object]:
    run_id = record.submission.run_id
    directory = publication.publication_directory(record.submission.runs_root, run_id)
    receipt = publication.latest_publication(directory)
    result: dict[str, object] = {
        "publication": receipt.model_dump(mode="json") if receipt else None
    }
    paths = sorted((directory / "observations").glob("*.json"))
    if paths:
        path = paths[-1]
        observation = collaboration.Observation.model_validate_json(path.read_bytes())
        if observation.run_id != run_id:
            raise ValueError("GitHub evidence belongs to another Run")
        result.update(observation_response(observation, path))
    return result


def github_command(record: RunView, action: str, body: bytes) -> dict[str, object]:
    run_id = record.submission.run_id
    root = record.submission.runs_root
    try:
        if action == "observe":
            observation, path = collaboration.observe_pull(root, run_id)
            return {"run_id": str(run_id), **observation_response(observation, path)}
        request = PublishRequest.model_validate_json(body)
        pull = publication.publish_run(
            run_id,
            approve=request.approve,
            expected_attempt=request.expected_attempt,
            destination=request.destination,
            base=request.base,
            expect_head=request.expect_head,
            runs_dir=root,
        )
        return {"run_id": str(run_id), "pull": pull.model_dump(mode="json")}
    except subprocess.SubprocessError as error:
        raise ValueError(
            f"GitHub {action} failed. Check GitHub CLI access and retry."
        ) from error
