"""JSONL trace writing helpers."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from slopgate.constants import METADATA_COMMAND
from slopgate._types import object_list
from slopgate.util.atomic_files import append_lines_locked
from slopgate.util import logger

DEFAULT_FLUSH_THRESHOLD = int("20")


def make_record(payload: Mapping[str, object]) -> str:
    record = {"timestamp": datetime.now(UTC).isoformat(), **dict(payload)}
    return json.dumps(record, sort_keys=True)


class TraceWriter:
    def __init__(
        self,
        trace_dir: Path,
        *,
        buffered: bool = False,
        flush_threshold: int = DEFAULT_FLUSH_THRESHOLD,
    ) -> None:
        self.trace_dir = trace_dir
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        (self.trace_dir / "async").mkdir(exist_ok=True)
        self._buffered = buffered
        self._flush_threshold = max(1, flush_threshold)
        self._pending: dict[str, list[str]] = defaultdict(list)

    def _write_lines(self, filename: str, lines: list[str]) -> None:
        target = self.trace_dir / filename
        try:
            append_lines_locked(target, lines)
        except OSError as exc:
            logger.warning("trace write failed", path=str(target), error=str(exc))

    def _append(self, filename: str, payload: Mapping[str, object]) -> None:
        line = f"{make_record(payload)}\n"
        if not self._buffered:
            self._write_lines(filename, [line])
            return
        pending = self._pending[filename]
        pending.append(line)
        if len(pending) >= self._flush_threshold:
            self._write_lines(filename, pending.copy())
            pending.clear()

    def flush(self) -> None:
        for filename, lines in list(self._pending.items()):
            if not lines:
                continue
            self._write_lines(filename, lines.copy())
            lines.clear()

    def event(self, payload: Mapping[str, object]) -> None:
        raw_event = payload.get("event_name")
        event_name = raw_event if isinstance(raw_event, str) else "unknown"
        logger.info(
            "trace event write",
            event_name=event_name,
            target="events.jsonl",
            buffered=self._buffered,
            trace_dir=str(self.trace_dir),
        )
        self._append("events.jsonl", payload)

    def rule(self, payload: Mapping[str, object]) -> None:
        raw_rule = payload.get("rule_id")
        raw_decision = payload.get("decision")
        logger.info(
            "trace rule write",
            rule_id=raw_rule if isinstance(raw_rule, str) else "unknown",
            decision=raw_decision if isinstance(raw_decision, str) else "unknown",
            target="rules.jsonl",
            buffered=self._buffered,
            trace_dir=str(self.trace_dir),
        )
        self._append("rules.jsonl", payload)

    def result(self, payload: Mapping[str, object]) -> None:
        findings = payload.get("findings")
        findings_count = (
            len(object_list(cast(list[object], findings)))
            if isinstance(findings, list)
            else 0
        )
        logger.info(
            "trace result write",
            findings_count=findings_count,
            target="results.jsonl",
            buffered=self._buffered,
            trace_dir=str(self.trace_dir),
        )
        self._append("results.jsonl", payload)

    def subprocess(
        self, payload: Mapping[str, object], *, async_mode: bool = False
    ) -> None:
        filename = "async/subprocess.jsonl" if async_mode else "subprocess.jsonl"
        command = payload.get(METADATA_COMMAND)
        logger.info(
            "trace subprocess write",
            command_present=isinstance(command, str) and bool(command),
            target=filename,
            async_mode=async_mode,
            buffered=self._buffered,
            trace_dir=str(self.trace_dir),
        )
        self._append(filename, payload)
