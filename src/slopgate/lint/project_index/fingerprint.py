"""Engine fingerprint used to invalidate the enrolled lint fact DB."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from slopgate.constants import LINT_INDEX_SCHEMA_VERSION


def engine_fingerprint(project_root: Path) -> str:
    """Hash engine version, schema, detector files, and effective lint config."""
    from slopgate.lint import __version__
    from slopgate.lint._config import get_config

    digest = hashlib.sha256()
    digest.update(__version__.encode("utf-8"))
    digest.update(str(LINT_INDEX_SCHEMA_VERSION).encode("ascii"))
    digest.update(_detector_tree_stamp(str(Path(__file__).resolve().parents[1])))
    cfg = get_config()
    payload = {
        "enabled_cli_rules": cfg.enabled_cli_rules,
        "max_complexity": cfg.max_complexity,
        "min_function_body_lines": cfg.min_function_body_lines,
        "min_call_sequence_length": cfg.min_call_sequence_length,
        "max_repeated_magic_numbers": cfg.max_repeated_magic_numbers,
        "max_repeated_string_literals": cfg.max_repeated_string_literals,
        "project_root": str(project_root),
    }
    digest.update(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _detector_tree_stamp(lint_root: str) -> bytes:
    digest = hashlib.sha256()
    root = Path(lint_root)
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        stat = path.stat()
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.digest()
