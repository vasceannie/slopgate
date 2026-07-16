"""Ordered full-read evidence shared by recovery validation."""

from __future__ import annotations

import json
from pathlib import Path
from time import time

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import METADATA_PATH, SESSION_ID

from .._keys import SessionStateMutationMixin


class RetryReadEvidenceMixin(SessionStateMutationMixin):
    def _retry_full_read_identity(self, session_id: str, path: str) -> ObjectDict:
        return {
            SESSION_ID: session_id.strip(),
            METADATA_PATH: self._normalize_path(path),
        }

    def record_retry_full_read(self, session_id: str, path: str) -> None:
        normalized_path = self._normalize_path(path)
        if not Path(normalized_path).exists():
            return
        key = json.dumps(
            self._retry_full_read_identity(session_id, normalized_path), sort_keys=True
        )
        with self._locked_state():
            state = self._load_state()
            sequence = state["event_sequence"] + 1
            state["full_reads"][key] = int(time())
            state["full_read_events"][key] = {
                "sequence": sequence,
                "timestamp": int(time()),
            }
            state["event_sequence"] = sequence
            self._save_state(state)

    def retry_full_read_sequence(self, session_id: str, path: str) -> int | None:
        key = json.dumps(
            self._retry_full_read_identity(session_id, path), sort_keys=True
        )
        sequence = object_dict(self._load_state()["full_read_events"].get(key)).get(
            "sequence"
        )
        return sequence if isinstance(sequence, int) else None
