"""Compile only captured Markdown into validated methodology documents."""

from dataclasses import dataclass
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict

from shipyard.configuration.yaml import UniqueKeySafeLoader
from shipyard.domain.execution import MethodologyAsset, Nonblank
from shipyard.domain.playbook import PlaybookDefinition, StageDefinition
from shipyard.domain.skill import MethodologyIdentity, SkillMetadata


class MethodologyError(ValueError):
    """Frozen methodology does not satisfy its declared identity or format."""


def _version_label(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return str(value)
    if isinstance(value, str):
        return value
    raise ValueError("Expected a string version or positive integer version")


type _Version = Annotated[Nonblank, BeforeValidator(_version_label)]


class _PlaybookHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["bounded-repository-change"]
    version: _Version
    stages: tuple[StageDefinition, ...]


class _SkillHeader(SkillMetadata):
    version: _Version


@dataclass(frozen=True)
class PlaybookDocument:
    asset: MethodologyAsset
    definition: PlaybookDefinition
    guidance: str

    @property
    def identity(self) -> MethodologyIdentity:
        return MethodologyIdentity(
            kind="playbook",
            name=self.asset.name,
            version=self.asset.version,
            sha256=self.asset.sha256,
        )


@dataclass(frozen=True)
class SkillDocument:
    asset: MethodologyAsset
    metadata: SkillMetadata
    guidance: str

    @property
    def identity(self) -> MethodologyIdentity:
        return MethodologyIdentity(
            kind="skill",
            name=self.asset.name,
            version=self.asset.version,
            sha256=self.asset.sha256,
        )


def _split_document(asset: MethodologyAsset) -> tuple[object, str]:
    lines = asset.content.removeprefix("\ufeff").splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("Methodology requires leading YAML front matter")
    closing = next(
        (
            index
            for index in range(1, len(lines))
            if lines[index].rstrip("\r\n") == "---"
        ),
        None,
    )
    if closing is None:
        raise ValueError("Unclosed methodology front matter")
    body = "".join(lines[closing + 1 :])
    if not body.strip():
        raise ValueError("Methodology requires nonblank Markdown guidance")
    return yaml.load("".join(lines[1:closing]), Loader=UniqueKeySafeLoader), body


def _check_identity(asset: MethodologyAsset, name: str, version: str) -> None:
    if asset.name != name or asset.version != version:
        raise ValueError("Header identity must match frozen asset name and version")


def parse_playbook(asset: MethodologyAsset) -> PlaybookDocument:
    try:
        asset = MethodologyAsset.model_validate(asset.model_dump())
        metadata, body = _split_document(asset)
        header = _PlaybookHeader.model_validate(metadata)
        _check_identity(asset, header.id, header.version)
        definition = PlaybookDefinition(
            name=header.id, version=header.version, stages=header.stages
        )
        return PlaybookDocument(asset=asset, definition=definition, guidance=body)
    except (ValueError, yaml.YAMLError) as error:
        raise MethodologyError(
            f"Cannot compile playbook {asset.name}@{asset.version}"
        ) from error


def parse_skill(asset: MethodologyAsset) -> SkillDocument:
    try:
        asset = MethodologyAsset.model_validate(asset.model_dump())
        metadata, body = _split_document(asset)
        header = _SkillHeader.model_validate(metadata)
        _check_identity(asset, header.id, header.version)
        return SkillDocument(
            asset=asset,
            metadata=SkillMetadata.model_validate(header.model_dump()),
            guidance=body,
        )
    except (ValueError, yaml.YAMLError) as error:
        raise MethodologyError(
            f"Cannot compile skill {asset.name}@{asset.version}"
        ) from error
