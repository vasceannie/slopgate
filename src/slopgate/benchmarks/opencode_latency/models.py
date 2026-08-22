"""Typed values for the OpenCode latency benchmark."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from slopgate._types import ObjectDict


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    repo: Path
    target: Path
    iterations: int
    warmup: int
    binary: str


@dataclass(frozen=True, slots=True)
class LatencySummary:
    minimum: float
    p50: float
    p95: float
    maximum: float

    @classmethod
    def from_values(cls, values: list[float]) -> LatencySummary:
        ordered = sorted(values)
        p50_index = max(0, math.ceil(0.50 * len(ordered)) - 1)
        p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
        return cls(
            minimum=round(ordered[0], 3),
            p50=round(ordered[p50_index], 3),
            p95=round(ordered[p95_index], 3),
            maximum=round(ordered[-1], 3),
        )

    def to_dict(self) -> ObjectDict:
        return {
            "minimum": self.minimum,
            "p50": self.p50,
            "p95": self.p95,
            "maximum": self.maximum,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    totals: list[float]
    outcomes: list[str]
    rows: list[ObjectDict]


@dataclass(frozen=True, slots=True)
class BenchmarkExecutionError(RuntimeError):
    message: str

    def __str__(self) -> str:
        return self.message
