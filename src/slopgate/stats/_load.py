"""Hook activity log loading helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from slopgate._types import object_dict

def _default_log_path() -> Path:
    """Find the results.jsonl log file."""
    from slopgate.config import config_dir

    xdg = config_dir() / "logs" / "results.jsonl"
    if xdg.exists():
        return xdg

    legacy = (
        Path.home()
        / ".claude"
        / "hooks"
        / "enforcer"
        / ".claude"
        / "hook-layer"
        / "logs"
        / "results.jsonl"
    )
    if legacy.exists():
        return legacy

    return xdg


def _parse_timestamp(ts_raw: str, cutoff: datetime | None) -> bool:
    """Return True if the entry should be skipped (before cutoff)."""
    if cutoff is None:
        return False
    try:
        return datetime.fromisoformat(ts_raw) < cutoff
    except (ValueError, TypeError):
        return False


parse_timestamp = _parse_timestamp


def load_entries(path: Path, days: int | None) -> list[dict[str, object]]:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None
    )
    entries: list[dict[str, object]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw_entry = cast(object, json.loads(stripped))
            except json.JSONDecodeError:
                continue
            entry = object_dict(raw_entry)
            if not entry:
                continue
            ts = entry.get("timestamp", "")
            if isinstance(ts, str) and _parse_timestamp(ts, cutoff):
                continue
            entries.append(entry)
    return entries
