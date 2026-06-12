from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading

from slopgate.models import RuntimeConfig

from ._discovery import detect_root, resolve_config_path
from ._io import load_json
from ._repo import ensure_worktree_enrollment, resolve_repo_root
from ._settings import merge_config, ensure_trace_directories

MISSING_CONFIG_MTIME_NS = -1
MISSING_CONFIG_SIZE = -1


@dataclass(frozen=True, slots=True)
class _ConfigFileSignature:
    path: Path
    mtime_ns: int
    size: int


@dataclass(frozen=True, slots=True)
class _RawConfigCacheEntry:
    signature: _ConfigFileSignature
    raw: dict[str, object]


_raw_config_cache: dict[Path, _RawConfigCacheEntry] = {}
_raw_config_cache_lock = threading.Lock()


def _config_file_signature(path: Path) -> _ConfigFileSignature:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return _ConfigFileSignature(path, MISSING_CONFIG_MTIME_NS, MISSING_CONFIG_SIZE)
    return _ConfigFileSignature(path, stat.st_mtime_ns, stat.st_size)


def _load_raw_config(config_path: Path) -> dict[str, object]:
    signature = _config_file_signature(config_path)
    with _raw_config_cache_lock:
        cached = _raw_config_cache.get(config_path)
    if cached is not None and cached.signature == signature:
        return dict(cached.raw)

    raw = load_json(config_path)
    with _raw_config_cache_lock:
        _raw_config_cache[config_path] = _RawConfigCacheEntry(signature, dict(raw))
    return raw


def load_config(
    root: Path | None = None,
    repo_root: Path | None = None,
    *,
    ensure_enrollment: bool = True,
    ensure_trace: bool = True,
) -> RuntimeConfig:
    """Load configuration with XDG discovery chain.

    Config is loaded from resolve_config_path(). Root is used for
    trace directory and prompt context file resolution.
    """
    actual_root = (root or detect_root()).resolve()
    config_path = resolve_config_path()
    raw = _load_raw_config(config_path)
    enrollment_root = (
        ensure_worktree_enrollment(repo_root) if ensure_enrollment else None
    )
    resolved_repo_root = (
        enrollment_root
        or resolve_repo_root(repo_root)
        or (repo_root.resolve() if repo_root is not None else Path.cwd().resolve())
    )
    config = merge_config(actual_root, raw, resolved_repo_root)
    if ensure_trace:
        ensure_trace_directories(config)
    return config
