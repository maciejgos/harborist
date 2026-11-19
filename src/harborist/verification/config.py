"""Parse the narrow verification YAML format with safe, unique-key mappings."""

import hashlib

import yaml
from pydantic import ValidationError

from harborist.configuration.yaml import UniqueKeySafeLoader
from harborist.domain import (
    GitCommitSha,
    VerificationConfig,
    VerificationConfigSnapshot,
)
from harborist.git import GitReadError, GitRepository


class VerificationConfigError(ValueError):
    """Verification configuration could not be read or validated."""


def parse_verification_config(source: bytes) -> VerificationConfig:
    """Validate source bytes without interpreting or executing command strings."""
    try:
        document = yaml.load(source.decode("utf-8"), Loader=UniqueKeySafeLoader)
        return VerificationConfig.model_validate(document)
    except (UnicodeDecodeError, yaml.YAMLError, ValidationError) as error:
        raise VerificationConfigError(
            "Cannot parse verification configuration harborist.yaml"
        ) from error


def load_verification_config(
    *, repository: GitRepository, base_sha: GitCommitSha
) -> VerificationConfigSnapshot:
    """Read fixed-base settings; never refresh HEAD or execute their commands."""
    try:
        try:
            source = repository.read_file_at_commit(
                commit_sha=base_sha, path="harborist.yaml"
            )
        except GitReadError:
            if repository.has_path_at_commit(
                commit_sha=base_sha, path="harborist.yaml"
            ):
                raise
            source = repository.read_file_at_commit(
                commit_sha=base_sha, path="shipyard.yaml"
            )
        return VerificationConfigSnapshot(
            base_sha=base_sha,
            source_sha256=hashlib.sha256(source).hexdigest(),
            config=parse_verification_config(source),
        )
    except (GitReadError, VerificationConfigError, ValidationError) as error:
        raise VerificationConfigError(
            f"Cannot load verification configuration harborist.yaml at {base_sha}"
        ) from error
