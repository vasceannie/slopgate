"""Trace-local parity snapshots for projected and authoritative lint."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from slopgate._types import object_dict, object_list
from slopgate.util.atomic_files import write_text_atomic_locked

PARITY_SCHEMA_VERSION = 1
PROJECTED_RULE_ID = "QUALITY-PROJECTED-LINT-001"


@dataclass(frozen=True, slots=True)
class ProjectionParitySnapshot:
    session_id: str
    paths: list[str]
    collector_ids: dict[str, list[str]]
    projection_digest: str


def _snapshot_path(trace_dir: Path, session_id: str, paths: list[str]) -> Path:
    identity = "\0".join((session_id, *sorted(paths)))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return trace_dir / "projected-lint" / f"{digest}.json"


def record_parity_snapshot(trace_dir: Path, snapshot: ProjectionParitySnapshot) -> None:
    snapshot_path = _snapshot_path(trace_dir, snapshot.session_id, snapshot.paths)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": PARITY_SCHEMA_VERSION,
        "projected_rule_id": PROJECTED_RULE_ID,
        "paths": sorted(snapshot.paths),
        "collector_ids": snapshot.collector_ids,
        "projection_digest": snapshot.projection_digest,
    }
    write_text_atomic_locked(
        snapshot_path,
        json.dumps(payload, sort_keys=True),
        prefix="projected-lint-",
        suffix=".json",
    )


def _collector_ids(value: object) -> dict[str, list[str]]:
    collectors: dict[str, list[str]] = {}
    for collector, raw_ids in object_dict(value).items():
        stable_ids = sorted(
            item for item in object_list(raw_ids) if isinstance(item, str)
        )
        if stable_ids:
            collectors[collector] = stable_ids
    return collectors


def _id_difference(
    left: dict[str, list[str]], right: dict[str, list[str]]
) -> dict[str, list[str]]:
    difference: dict[str, list[str]] = {}
    for collector in sorted(left.keys() | right.keys()):
        values = sorted(set(left.get(collector, ())) - set(right.get(collector, ())))
        if values:
            difference[collector] = values
    return difference


def pop_parity_snapshot(
    trace_dir: Path,
    session_id: str,
    paths: list[str],
    authoritative_ids: dict[str, list[str]],
) -> dict[str, object] | None:
    snapshot_path = _snapshot_path(trace_dir, session_id, paths)
    try:
        payload = object_dict(json.loads(snapshot_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    finally:
        snapshot_path.unlink(missing_ok=True)
    if payload.get("schema_version") != PARITY_SCHEMA_VERSION:
        return None
    projected_ids = _collector_ids(payload.get("collector_ids"))
    return {
        "authority": "post_edit",
        "projected_rule_id": PROJECTED_RULE_ID,
        "status": "match" if projected_ids == authoritative_ids else "mismatch",
        "paths": sorted(paths),
        "projection_digest": payload.get("projection_digest"),
        "projected_collector_ids": projected_ids,
        "authoritative_collector_ids": authoritative_ids,
        "missing_after_edit": _id_difference(projected_ids, authoritative_ids),
        "unexpected_after_edit": _id_difference(authoritative_ids, projected_ids),
    }


__all__ = [
    "ProjectionParitySnapshot",
    "PROJECTED_RULE_ID",
    "pop_parity_snapshot",
    "record_parity_snapshot",
]
