"""Shared captures for repair CLI tests."""

from __future__ import annotations

from pathlib import Path
from time import time

from slopgate._types import ObjectDict
from slopgate.state import HookStateStore
from tests.repair_cli.constants import REPAIR_REQUIRED_STATUS


class ScopedLintCapture:
    """Capture scoped lint arguments while returning a configured status."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[tuple[Path, tuple[ObjectDict, ...]]] = []

    def __call__(self, cwd: Path, targets: list[ObjectDict]) -> int:
        self.calls.append((cwd, tuple(dict(target) for target in targets)))
        return self.returncode


class WritableRepairStateStore(HookStateStore):
    """Store facade that can persist a raw repair record for shape tests."""

    def save_repair_record(self, record: ObjectDict) -> None:
        with self._locked_state():
            state = self._load_state()
            state["repair_required"] = record
            self._save_state(state)


def legacy_repair_record(
    *,
    generation: str,
    paths: list[str],
    rule_ids: list[str],
) -> ObjectDict:
    """Repair record written by releases predating worktree/target provenance."""
    return {
        "status": REPAIR_REQUIRED_STATUS,
        "generation": generation,
        "session_id": "session-one",
        "call_id": "call-one",
        "rule_ids": sorted(rule_ids),
        "paths": sorted(paths),
        "timestamp": int(time()),
    }
