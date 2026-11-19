"""Digest-checked immutable PACKAGE indexes shared by application and reuse."""

import hashlib
import stat
from pathlib import Path, PurePosixPath

from harborist.evidence.package import RunEvidence


def regular(path: Path) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"Evidence must be a regular file: {path}")
    return path.read_bytes()


def load_index(directory: Path) -> tuple[RunEvidence, dict[str, bytes]]:
    if directory.is_symlink():
        raise ValueError("Run directory must not be a symlink")
    evidence = RunEvidence.model_validate_json(regular(directory / "evidence.json"))
    if evidence.version != 1:
        raise ValueError("Unsupported evidence version")
    indexed: dict[str, bytes] = {}
    for entry in evidence.files:
        relative = PurePosixPath(entry.path)
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != entry.path
            or entry.path in indexed
            or relative.parts[0] == "workspace"
            or entry.path == "evidence.json"
        ):
            raise ValueError(f"Unsafe or duplicate evidence path: {entry.path}")
        path = directory
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                raise ValueError(f"Evidence symlink: {path}")
        raw = regular(path)
        if (
            len(raw) != entry.size_bytes
            or hashlib.sha256(raw).hexdigest() != entry.sha256
        ):
            raise ValueError(f"Evidence length/digest mismatch: {entry.path}")
        indexed[entry.path] = raw

    return evidence, indexed
