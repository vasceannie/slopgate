"""Deterministic privacy-safe aggregate failure-profile storage."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.constants import UNKNOWN_VALUE
from slopgate.models import FailureProfileConfig
from slopgate.policy_defaults import FAILURE_PROFILE_DECAY_PRECISION
from slopgate.util.atomic_files import locked_path

from ._models import (
    FailureProfileDimension,
    FailureProfileEntry,
    FailureProfileSnapshot,
    FailureRisk,
    ResolutionOutcome,
)


PROFILE_SCHEMA_VERSION: Final = 1
PROFILE_DIRECTORY: Final = "failure-profiles"
MIN_RECURRING_COUNT: Final = 2.0
MIN_GUIDANCE_RISKS: Final = 3
MAX_GUIDANCE_RISKS: Final = 5


@dataclass(frozen=True, slots=True)
class _StoredEntry:
    dimension: FailureProfileDimension
    daily_counts: dict[str, int]


class FailureProfileStore:
    def __init__(
        self, trace_dir: Path, repo_root: Path, config: FailureProfileConfig
    ) -> None:
        self._config = config
        self.scope_id = hashlib.sha256(
            str(repo_root.resolve(strict=False)).encode("utf-8")
        ).hexdigest()
        self.path = trace_dir / PROFILE_DIRECTORY / f"{self.scope_id}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        dimension: FailureProfileDimension,
        *,
        today: date | None = None,
        count: int = 1,
    ) -> None:
        if not self._config.enabled or count < 1:
            return
        current_day = today or datetime.now(UTC).date()
        with locked_path(self.path):
            entries = self._load_entries()
            daily_counts = dict(entries.get(dimension, {}))
            day_key = current_day.isoformat()
            daily_counts[day_key] = daily_counts.get(day_key, 0) + count
            entries[dimension] = daily_counts
            self._write_entries(self._normalized(entries, current_day))

    def snapshot(self, *, today: date | None = None) -> FailureProfileSnapshot:
        current_day = today or datetime.now(UTC).date()
        with locked_path(self.path):
            normalized = self._normalized(self._load_entries(), current_day)
            if self.path.exists():
                self._write_entries(normalized)
        entries = tuple(
            FailureProfileEntry(
                dimension=dimension,
                decayed_count=self._decayed_count(daily_counts, current_day),
                last_seen=max(daily_counts),
            )
            for dimension, daily_counts in sorted(
                normalized.items(), key=lambda item: item[0].sort_key()
            )
        )
        return FailureProfileSnapshot(self.scope_id, entries)

    def top_risks(self, *, today: date | None = None) -> tuple[FailureRisk, ...]:
        grouped: dict[tuple[str, str, str], float] = {}
        for entry in self.snapshot(today=today).entries:
            if entry.dimension.resolution_outcome != "blocked":
                continue
            key = (
                entry.dimension.rule_id,
                entry.dimension.path_role,
                entry.dimension.language,
            )
            grouped[key] = grouped.get(key, 0.0) + entry.decayed_count
        ranked = sorted(
            (
                FailureRisk(
                    rule_id,
                    path_role,
                    language,
                    round(count, FAILURE_PROFILE_DECAY_PRECISION),
                )
                for (rule_id, path_role, language), count in grouped.items()
                if count >= MIN_RECURRING_COUNT
            ),
            key=lambda risk: (
                -risk.decayed_count,
                risk.rule_id,
                risk.path_role,
                risk.language,
            ),
        )
        if len(ranked) < MIN_GUIDANCE_RISKS:
            return ()
        return tuple(ranked[:MAX_GUIDANCE_RISKS])

    def clear(self) -> None:
        with locked_path(self.path):
            try:
                self.path.unlink()
            except FileNotFoundError:
                return

    def _load_entries(self) -> dict[FailureProfileDimension, dict[str, int]]:
        try:
            raw = object_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        if raw.get("schema_version") != PROFILE_SCHEMA_VERSION:
            return {}
        entries: dict[FailureProfileDimension, dict[str, int]] = {}
        for item in object_list(raw.get("entries")):
            parsed = _parse_stored_entry(object_dict(item))
            if parsed is not None:
                entries[parsed.dimension] = parsed.daily_counts
        return entries

    def _normalized(
        self,
        entries: dict[FailureProfileDimension, dict[str, int]],
        today: date,
    ) -> dict[FailureProfileDimension, dict[str, int]]:
        retained = {
            dimension: counts
            for dimension, raw_counts in entries.items()
            if (counts := self._retained_counts(raw_counts, today))
        }
        ranked = sorted(
            retained.items(),
            key=lambda item: (
                -self._decayed_count(item[1], today),
                -date.fromisoformat(max(item[1])).toordinal(),
                item[0].sort_key(),
            ),
        )
        return dict(ranked[: self._config.max_entries])

    def _retained_counts(self, counts: dict[str, int], today: date) -> dict[str, int]:
        retained: dict[str, int] = {}
        for day_text, count in counts.items():
            try:
                age = (today - date.fromisoformat(day_text)).days
            except ValueError:
                continue
            if 0 <= age < self._config.retention_days and count > 0:
                retained[day_text] = count
        return retained

    def _decayed_count(self, counts: dict[str, int], today: date) -> float:
        weighted = sum(
            count
            * (self._config.retention_days - (today - date.fromisoformat(day)).days)
            / self._config.retention_days
            for day, count in counts.items()
        )
        return round(weighted, FAILURE_PROFILE_DECAY_PRECISION)

    def _write_entries(
        self, entries: dict[FailureProfileDimension, dict[str, int]]
    ) -> None:
        payload: ObjectDict = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "scope_id": self.scope_id,
            "entries": [
                dimension.to_json(dict(sorted(counts.items())))
                for dimension, counts in sorted(
                    entries.items(), key=lambda item: item[0].sort_key()
                )
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.scope_id}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _parse_stored_entry(raw: ObjectDict) -> _StoredEntry | None:
    outcome = _resolution_outcome(raw.get("resolution_outcome"))
    rule_id = string_value(raw.get("rule_id"))
    if not rule_id or outcome is None:
        return None
    dimension = FailureProfileDimension(
        rule_id=rule_id,
        path_role=string_value(raw.get("path_role")) or "pathless",
        language=string_value(raw.get("language")) or UNKNOWN_VALUE,
        platform=string_value(raw.get("platform")) or UNKNOWN_VALUE,
        model_identifier=string_value(raw.get("model_identifier")) or None,
        resolution_outcome=outcome,
    )
    counts = {
        day: count
        for day, count in object_dict(raw.get("daily_counts")).items()
        if isinstance(count, int)
    }
    return _StoredEntry(dimension, counts)


def _resolution_outcome(value: object) -> ResolutionOutcome | None:
    match value:
        case "blocked":
            return "blocked"
        case "resolved":
            return "resolved"
        case _:
            return None
