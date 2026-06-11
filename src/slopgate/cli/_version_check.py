"""Lightweight version-check for slopgate lint output.

Checks PyPI for a newer release and appends a non-blocking notice to CLI
output.  Results are cached for 6 hours to avoid network overhead on every
invocation.  The check is skipped entirely in CI and non-interactive
environments.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from slopgate._types import object_dict

CACHE_TTL_SECONDS = 3600 * 6  # 6 hours
_CACHE_DIR = Path.home() / ".local" / "share" / "slopgate"
_CACHE_PATH = _CACHE_DIR / "version-cache.json"

_PYPI_URL = "https://pypi.org/pypi/ai-slopgate/json"
_REQUEST_TIMEOUT = 3


@dataclass(frozen=True, slots=True)
class VersionInfo:
    current: str
    latest: str | None
    checked_at: float


def _should_skip_check() -> bool:
    """Skip in CI and non-interactive environments."""
    if os.environ.get("CI"):
        return True
    if not (hasattr(sys.stderr, "isatty") and sys.stderr.isatty()):
        return True
    return False


def _fetch_latest_version() -> str | None:
    req = urllib.request.Request(
        _PYPI_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "slopgate-version-check",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return _version_from_payload(json.loads(resp.read()))
    except (
        json.JSONDecodeError,
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        urllib.error.URLError,
    ):
        return None


def _version_from_payload(payload: object) -> str | None:
    payload_dict = object_dict(payload)
    if not payload_dict:
        return None
    info = object_dict(payload_dict.get("info"))
    if not info:
        return None
    version = info.get("version")
    if not isinstance(version, str) or not version:
        return None
    return version


def _cache_from_payload(payload: object) -> VersionInfo | None:
    payload_dict = object_dict(payload)
    if not payload_dict:
        return None
    checked_at = payload_dict.get("checked_at")
    if not isinstance(checked_at, int | float):
        return None
    if time.time() - checked_at >= CACHE_TTL_SECONDS:
        return None
    latest = payload_dict.get("latest")
    cached_latest = latest if isinstance(latest, str) else None
    return VersionInfo(current="", latest=cached_latest, checked_at=float(checked_at))


def _read_cache() -> VersionInfo | None:
    if not _CACHE_PATH.exists():
        return None
    try:
        return _cache_from_payload(json.loads(_CACHE_PATH.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, UnicodeDecodeError):
        return None


def _write_cache(latest: str) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"latest": latest, "checked_at": time.time()})
        _CACHE_PATH.write_text(payload, encoding="utf-8")
    except OSError:
        return


def check_version(current: str) -> VersionInfo:
    """Return version info, using cache when fresh.

    Skips network entirely in CI/non-interactive environments.
    """
    if _should_skip_check():
        return VersionInfo(current=current, latest=None, checked_at=time.time())

    cached = _read_cache()
    if cached is not None:
        return VersionInfo(
            current=current,
            latest=cached.latest,
            checked_at=cached.checked_at,
        )

    latest = _fetch_latest_version()
    if latest is not None:
        _write_cache(latest)
    return VersionInfo(current=current, latest=latest, checked_at=time.time())


def format_update_notice(current: str, latest: str | None) -> str | None:
    """Return a user-facing update notice, or None if no update is available."""
    if latest is None:
        return None
    if latest == current:
        return None
    return f"update:   {latest} available — run `slopgate update` to upgrade"
