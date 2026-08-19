"""Engine fingerprint used to invalidate the enrolled lint fact DB."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from functools import lru_cache
from pathlib import Path

from typing import TYPE_CHECKING, TypeAlias

from slopgate.constants import LINT_INDEX_SCHEMA_VERSION

if TYPE_CHECKING:
    from slopgate.lint._config import QualityConfig

ConfigValue: TypeAlias = (
    Path
    | None
    | str
    | int
    | float
    | bool
    | tuple[Path, ...]
    | set[str]
    | set[int]
    | list[str]
    | tuple[str, ...]
    | list[tuple[str, str]]
    | dict[str, bool]
)
CanonicalConfigValue: TypeAlias = (
    ConfigValue | tuple[str, ...] | tuple[tuple[str, bool], ...]
)


def engine_fingerprint(project_root: Path) -> str:
    """Hash engine version, schema, detector files, and effective lint config."""
    from slopgate.lint import __version__
    from slopgate.lint._config import get_config

    digest = hashlib.sha256()
    digest.update(__version__.encode("utf-8"))
    digest.update(str(LINT_INDEX_SCHEMA_VERSION).encode("ascii"))
    digest.update(_detector_tree_stamp(str(Path(__file__).resolve().parents[1])))
    cfg = get_config()
    payload = [
        *_config_payload(cfg),
        ("cli_regex_rules", repr(_regex_config_payload(project_root))),
        ("fingerprint_project_root", str(project_root)),
    ]
    digest.update(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


def _config_payload(cfg: QualityConfig) -> list[tuple[str, str]]:
    """Return every resolved lint setting in deterministic form."""
    payload: list[tuple[str, str]] = []
    for field in fields(cfg):
        value: ConfigValue = getattr(cfg, field.name)
        payload.append((field.name, repr(_canonical_config_value(value))))
    return payload


def _canonical_config_value(value: ConfigValue) -> CanonicalConfigValue:
    if isinstance(value, set):
        return tuple(sorted((repr(item) for item in value)))
    if isinstance(value, dict):
        return tuple(sorted(value.items()))
    return value


def _regex_config_payload(
    project_root: Path,
) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    """Return active CLI regex definitions in deterministic form."""
    from slopgate.lint._regex_rules import cli_regex_rule_configs

    payload: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for config in cli_regex_rule_configs(project_root):
        values: list[tuple[str, str]] = []
        for field in fields(config):
            value: ConfigValue = getattr(config, field.name)
            values.append((field.name, repr(value)))
        payload.append((config.rule_id, tuple(values)))
    return payload


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
