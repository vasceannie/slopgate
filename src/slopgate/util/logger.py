from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Protocol


class _LogFn(Protocol):
    def __call__(self, message: str, **fields: object) -> None: ...


def _emit(level: str, message: str, **fields: object) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        **fields,
    }
    _ = sys.stderr.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _logger(level: str) -> _LogFn:
    def log(message: str, **fields: object) -> None:
        _emit(level, message, **fields)

    return log


debug, info, warning, error = (_logger(level) for level in ("debug", "info", "warning", "error"))
