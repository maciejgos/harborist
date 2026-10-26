"""Parse the narrow verification YAML format with safe, unique-key mappings."""

import hashlib
from collections.abc import Hashable

import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node, ScalarNode

from shipyard.domain import GitCommitSha, VerificationConfig, VerificationConfigSnapshot
from shipyard.git import GitReadError, GitRepository


class VerificationConfigError(ValueError):
    """Verification configuration could not be read or validated."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(
        self, node: Node, deep: bool = False
    ) -> dict[Hashable, object]:
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None, "Expected a mapping", node.start_mark)
        self.flatten_mapping(node)
        seen: set[str] = set()
        for key_node, _ in node.value:
            if (
                not isinstance(key_node, ScalarNode)
                or key_node.tag != "tag:yaml.org,2002:str"
            ):
                raise ConstructorError(
                    None, None, "Expected a string mapping key", key_node.start_mark
                )
            if key_node.value in seen:
                raise ConstructorError(
                    None, None, "Duplicate mapping key", key_node.start_mark
                )
            seen.add(key_node.value)
        return super().construct_mapping(node, deep=deep)


def parse_verification_config(source: bytes) -> VerificationConfig:
    """Validate source bytes without interpreting or executing command strings."""
    try:
        document = yaml.load(source.decode("utf-8"), Loader=_UniqueKeySafeLoader)
        return VerificationConfig.model_validate(document)
    except (UnicodeDecodeError, yaml.YAMLError, ValidationError) as error:
        raise VerificationConfigError(
            "Cannot parse verification configuration shipyard.yaml"
        ) from error


def load_verification_config(
    *, repository: GitRepository, base_sha: GitCommitSha
) -> VerificationConfigSnapshot:
    """Read fixed-base settings; never refresh HEAD or execute their commands."""
    try:
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
            f"Cannot load verification configuration shipyard.yaml at {base_sha}"
        ) from error
