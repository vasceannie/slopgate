"""Typed aggregate failure-profile values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from slopgate._types import ObjectDict
from slopgate.constants import METADATA_PLATFORM, METADATA_RULE_ID


ResolutionOutcome = Literal["blocked", "resolved"]


@dataclass(frozen=True, slots=True)
class FailureProfileDimension:
    rule_id: str
    path_role: str
    language: str
    platform: str
    model_identifier: str | None
    resolution_outcome: ResolutionOutcome

    def sort_key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.rule_id,
            self.path_role,
            self.language,
            self.platform,
            self.model_identifier or "",
            self.resolution_outcome,
        )

    def to_json(self, daily_counts: dict[str, int]) -> ObjectDict:
        return {
            METADATA_RULE_ID: self.rule_id,
            "path_role": self.path_role,
            "language": self.language,
            METADATA_PLATFORM: self.platform,
            "model_identifier": self.model_identifier,
            "resolution_outcome": self.resolution_outcome,
            "daily_counts": daily_counts,
        }


@dataclass(frozen=True, slots=True)
class FailureProfileEntry:
    dimension: FailureProfileDimension
    decayed_count: float
    last_seen: str

    def to_json(self) -> ObjectDict:
        return {
            **self.dimension.to_json({}),
            "decayed_count": self.decayed_count,
            "last_seen": self.last_seen,
        }


@dataclass(frozen=True, slots=True)
class FailureRisk:
    rule_id: str
    path_role: str
    language: str
    decayed_count: float

    def to_json(self) -> ObjectDict:
        return {
            METADATA_RULE_ID: self.rule_id,
            "path_role": self.path_role,
            "language": self.language,
            "decayed_count": self.decayed_count,
        }


@dataclass(frozen=True, slots=True)
class FailureProfileSnapshot:
    scope_id: str
    entries: tuple[FailureProfileEntry, ...]
