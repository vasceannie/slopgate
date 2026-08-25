"""Typed values for OpenCode mutation projections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TypeAlias

from slopgate._types import ObjectDict, ObjectMapping
from slopgate.constants import METADATA_CONTENT, METADATA_PATH
from slopgate.util import logger

OPENCODE_TOOL_CONTRACT_VERSION: Final = "slopgate-opencode-projection-v1"
PROJECTION_KEY: Final = "_slopgate_projection"

ProjectionStatus: TypeAlias = Literal[
    "projected", "invalid", "stale", "unsupported", "protocol_mismatch"
]
ProjectionReason: TypeAlias = Literal["update_hunk_mismatch"]
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
        logger.debug("OpenCode projected file serialized", path=self.path)
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
    reason: ProjectionReason | None = None
    target_path: str | None = None

    def to_dict(self) -> ObjectDict:
        logger.debug("OpenCode projection serialized", status=self.status)
        result: ObjectDict = {
            "status": self.status,
            "contract_version": OPENCODE_TOOL_CONTRACT_VERSION,
            "files": [item.to_dict() for item in self.files],
        }
        if self.reason is not None:
            result["reason"] = self.reason
        if self.target_path is not None:
            result[METADATA_PATH] = self.target_path
        return result


@dataclass(frozen=True, slots=True)
class PatchSection:
    operation: PatchOperation
    path: str
    lines: tuple[str, ...]
    move_to: str | None = None
