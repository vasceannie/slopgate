"""Typed values for OpenCode mutation projections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

from slopgate._types import ObjectDict, ObjectMapping
from slopgate.constants import METADATA_CONTENT, METADATA_PATH

OPENCODE_TOOL_CONTRACT_VERSION: Final = "slopgate-opencode-projection-v1"
PROJECTION_KEY: Final = "_slopgate_projection"

ProjectionStatus: TypeAlias = Literal[
    "projected", "invalid", "stale", "unsupported", "protocol_mismatch"
]
SnapshotStatus: TypeAlias = Literal["invalid", "missing", "stale"]
PatchOperation: TypeAlias = Literal["add", "update", "delete"]


@dataclass(frozen=True, slots=True)
class ProjectionRequest:
    tool_name: str
    tool_input: ObjectMapping
    root: Path
    contract_version: str


@dataclass(frozen=True, slots=True)
class Snapshot:
    content: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ProjectedFile:
    path: str
    content: str
    operation: str
    preimage_sha256: str | None

    def to_dict(self) -> ObjectDict:
        return {
            METADATA_PATH: self.path,
            METADATA_CONTENT: self.content,
            "operation": self.operation,
            "preimage_sha256": self.preimage_sha256,
        }


@dataclass(frozen=True, slots=True)
class Projection:
    status: ProjectionStatus
    files: tuple[ProjectedFile, ...] = ()

    def to_dict(self) -> ObjectDict:
        return {
            "status": self.status,
            "contract_version": OPENCODE_TOOL_CONTRACT_VERSION,
            "files": [item.to_dict() for item in self.files],
        }


@dataclass(frozen=True, slots=True)
class PatchSection:
    operation: PatchOperation
    path: str
    lines: tuple[str, ...]
