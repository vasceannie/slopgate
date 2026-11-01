"""Current-engine overlay rows: a sidecar keyed by ``case_id``."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from slopgate._types import ObjectDict
from slopgate.constants import ERROR_KEY

CLEAN_PRIMARY_RULE = "_CLEAN"


@dataclass(frozen=True, slots=True)
class OverlayProvenance:
    """Where and when an overlay row's verdict was produced."""

    engine_version: str
    evaluated_at: str
    cwd_kind: str = "enrolled_temp"
    schema_version: int = 1


def overlay_row_from_eval(
    case: ObjectDict, result: ObjectDict, provenance: OverlayProvenance
) -> ObjectDict:
    """Sidecar row keyed by ``case_id``. Does not mutate historical ``expected``."""
    got_rules = result.get("got_rules")
    current = [str(item) for item in got_rules] if isinstance(got_rules, list) else []
    return {
        "schema_version": provenance.schema_version,
        "case_id": case.get("case_id"),
        "engine_version": provenance.engine_version,
        "evaluated_at": provenance.evaluated_at,
        "cwd_kind": provenance.cwd_kind,
        "current_rules": current,
        "primary_rule_current": current[0] if current else CLEAN_PRIMARY_RULE,
        "primary_hit": bool(result.get("primary_hit")),
        "exact_match": bool(result.get("exact_rule_set_match")),
        ERROR_KEY: result.get(ERROR_KEY),
        "replayable": bool(result.get("replayable")),
    }


def write_overlay_jsonl(path: Path | str, rows: Sequence[ObjectDict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
