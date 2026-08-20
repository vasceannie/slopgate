"""Deterministic provenance fingerprints for result trace rows.

``effective_policy_fingerprint`` hashes resolved enforcement behavior: rule
source content, rule enablement, surface actions, severity overrides, regex
definitions, thresholds, and skip/disable semantics.
``guidance_fingerprint`` hashes runtime guidance material Slopgate can emit.
Both store only SHA256 digests, never raw configuration, so traces stay
secret-free.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
from dataclasses import fields
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from slopgate._types import is_object_dict, object_list
from slopgate.constants import RULE_ID_KEY
from slopgate.models import RegexRuleConfig, RuleSurfaceConfig

if TYPE_CHECKING:
    from slopgate.models import RuntimeConfig

_ENGINE_ROOT = Path(__file__).resolve().parent
_PACKAGE_ROOT = _ENGINE_ROOT.parent
_RULES_ROOT = _PACKAGE_ROOT / "rules"
_NON_ENFORCING_SOURCE_DIRS = frozenset({"_staging", "__pycache__"})

_GUIDANCE_SOURCE_FILES = (
    _ENGINE_ROOT / "_hints" / "constants.py",
    _ENGINE_ROOT / "_hints" / "core.py",
    _ENGINE_ROOT / "_hints" / "quality.py",
    _PACKAGE_ROOT / "rules" / "common" / "quality" / "guidance.py",
)

# RuntimeConfig fields that are infrastructure or guidance, not enforcement.
_POLICY_EXCLUDED_FIELDS = frozenset(
    {
        "root",
        "repo_root",
        "trace_dir",
        "prompt_context_files",
        "search_reminder_message",
        "hook_project_logger_import",
        "hook_project_logger_usage",
        "hook_quality_check_command",
    }
)

# RegexRuleConfig fields that affect matching or decisions; wording is
# guidance and is covered by guidance_fingerprint instead.
_REGEX_ENFORCEMENT_FIELDS = (
    RULE_ID_KEY,
    "severity",
    "events",
    "target",
    "action",
    "patterns",
    "path_globs",
    "exclude_path_globs",
    "tool_matchers",
    "case_sensitive",
    "multiline",
)


def slopgate_version() -> str:
    """Return the package version recorded on result rows."""
    from slopgate import __version__

    return __version__


def effective_policy_fingerprint(
    config: RuntimeConfig, *, rules_root: Path | None = None
) -> str:
    """Hash enforcement-relevant rule sources and resolved configuration."""
    payload = {
        "kind": "effective_policy",
        "rules_source": _source_digest(rules_root or _RULES_ROOT),
        "config": _policy_config_payload(config),
    }
    return _stable_digest(payload)


def guidance_fingerprint(config: RuntimeConfig) -> str:
    """Hash runtime guidance material selectable during evaluation."""
    payload = {
        "kind": "guidance",
        "guidance_sources": [_file_digest(path) for path in _GUIDANCE_SOURCE_FILES],
        "configured_rule_guidance": [
            {
                RULE_ID_KEY: rule.rule_id,
                "title": rule.title,
                "message": rule.message,
                "additional_context": rule.additional_context,
            }
            for rule in config.regex_rules
        ],
        "config": {
            "search_reminder_message": config.search_reminder_message,
            "hook_project_logger_import": config.hook_project_logger_import,
            "hook_project_logger_usage": config.hook_project_logger_usage,
            "hook_quality_check_command": config.hook_quality_check_command,
        },
        "prompt_context": [
            _file_digest(Path(expanded))
            for expanded in _existing_files(config.prompt_context_files)
        ],
    }
    return _stable_digest(payload)


def _policy_config_payload(config: RuntimeConfig) -> dict[str, object]:
    payload: dict[str, object] = {}
    for spec in fields(type(config)):
        if spec.name in _POLICY_EXCLUDED_FIELDS:
            continue
        payload[spec.name] = _canonical_policy_value(getattr(config, spec.name))
    return payload


def _canonical_policy_value(value: object) -> object:
    if isinstance(value, RegexRuleConfig):
        return {name: getattr(value, name) for name in _REGEX_ENFORCEMENT_FIELDS}
    if isinstance(value, RuleSurfaceConfig):
        return {
            "hook": {
                "enabled": value.hook.enabled,
                "events": list(value.hook.events),
                "action": value.hook.action,
            },
            "cli": {"enabled": value.cli.enabled},
        }
    if is_object_dict(value):
        mapping = value
        return {
            key: _canonical_policy_value(item)
            for key, item in sorted(mapping.items())
        }
    sequence = object_list(value)
    if sequence or isinstance(value, (list, tuple)):
        return [_canonical_policy_value(item) for item in sequence]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _existing_files(paths: list[str]) -> list[str]:
    existing: list[str] = []
    for raw in paths:
        expanded = raw.strip()
        if not expanded:
            continue
        candidate = Path(expanded).expanduser()
        if not candidate.is_absolute():
            continue
        if candidate.is_file():
            existing.append(str(candidate))
    return existing


def _stable_digest(payload: object) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source_digest(root: Path) -> str:
    root_text = str(root)
    return _tree_digest(root_text, _tree_stamp(root_text))


def _tree_stamp(root: str) -> tuple[tuple[str, int, int], ...]:
    base = Path(root)
    if not base.is_dir():
        return ()
    stamp: list[tuple[str, int, int]] = []
    for directory, names, filenames in os.walk(base):
        names[:] = sorted(
            name
            for name in names
            if not name.startswith(".") and name not in _NON_ENFORCING_SOURCE_DIRS
        )
        directory_path = Path(directory)
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = directory_path / filename
            stat = path.stat()
            rel = path.relative_to(base).as_posix()
            stamp.append((rel, stat.st_size, stat.st_mtime_ns))
    return tuple(stamp)


@lru_cache
def _tree_digest(root: str, stamp: tuple[tuple[str, int, int], ...]) -> str:
    digest = hashlib.sha256()
    base = Path(root)
    for rel, _size, _mtime_ns in stamp:
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        try:
            content = (base / rel).read_bytes()
        except OSError:
            content = b""
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _file_digest(path: Path) -> str:
    path_text = str(path)
    stat_key = _file_stat_key(path_text)
    if stat_key is None:
        return "missing"
    return _cached_file_digest(path_text, *stat_key)


def _file_stat_key(path: str) -> tuple[int, int] | None:
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


@lru_cache
def _cached_file_digest(path: str, size: int, mtime_ns: int) -> str:
    _ = size, mtime_ns
    try:
        content = Path(path).read_bytes()
    except OSError:
        return "missing"
    return hashlib.sha256(content).hexdigest()


def normalize_trace_path(raw: str) -> str:
    """POSIX-normalize a path for deterministic digest inputs."""
    return posixpath.normpath(raw.replace("\\", "/"))
