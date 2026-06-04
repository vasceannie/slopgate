"""Internal data models for quality enrichers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ImportableConstant:
    name: str
    value: int | float | str
    path: Path
    lineno: int


@dataclass(frozen=True, slots=True)
class MagicNumberHint:
    path: str
    lineno: int
    value: int | float
