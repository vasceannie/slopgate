"""Tests for platform adapters — input normalisation + output rendering.

Tests cover:
  1. Claude adapter backward compatibility (same output as before)
  2. Codex adapter input/output shapes
  3. OpenCode adapter input normalisation and output shapes
  4. Cross-platform: same payload → same findings, different output format
  5. Unsupported events produce None on restricted platforms
  6. Edge cases: mixed decisions, empty messages, mutation safety, combined
     context+decision, fixture replay through full engine pipeline
"""

from __future__ import annotations
from collections.abc import Callable
import json
from pathlib import Path
from typing import cast
import pytest
from slopgate._types import ObjectDict, object_dict, string_value
from slopgate.adapters import ADAPTERS, get_adapter
from slopgate.adapters.base import PlatformAdapter
from slopgate.adapters.claude import ClaudeAdapter
from slopgate.adapters.codex import CodexAdapter
from slopgate.adapters.cursor import CursorAdapter
from slopgate.adapters.opencode import OpenCodeAdapter
import slopgate.engine
from slopgate.engine import evaluate_payload
from slopgate.models import RuleFinding, Severity
from tests import support

engine_module = slopgate.engine

FIXTURES_DIR = support.BUNDLE_ROOT / "fixtures"
_RESOURCES_DIR = support.BUNDLE_ROOT / "src" / "slopgate" / "resources"


def load_platform_fixture(platform: str, fixture_name: str) -> ObjectDict:
    fixture_path = FIXTURES_DIR / platform / fixture_name
    return object_dict(cast(object, json.loads(fixture_path.read_text())))


def repo_with_quality_gate(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    return repo


def config_with_enabled_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *rule_ids: str
) -> None:
    raw = json.loads((_RESOURCES_DIR / "defaults.json").read_text(encoding="utf-8"))
    enabled = dict(raw.get("enabled_rules", {}))
    for rule_id in rule_ids:
        enabled[rule_id] = True
    raw["enabled_rules"] = enabled
    config_path = tmp_path / "adapter-spec-config.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))


def require_rendered(output: ObjectDict | None) -> ObjectDict:
    assert output is not None, "Expected rendered adapter output, got None"
    return output


def require_spec(output: ObjectDict | None) -> ObjectDict:
    rendered = require_rendered(output)
    spec = object_dict(rendered.get("hookSpecificOutput"))
    assert spec, f"Expected hookSpecificOutput, got: {rendered}"
    return spec


def require_nested(mapping: ObjectDict, key: str) -> ObjectDict:
    nested = object_dict(mapping.get(key))
    assert nested, f"Expected nested mapping at {key!r}, got: {mapping}"
    return nested


def rendered_string(mapping: ObjectDict, key: str, default: str = "") -> str:
    value = string_value(mapping.get(key))
    return value if value is not None else default


__all__ = (
    "ADAPTERS",
    "Callable",
    "ClaudeAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "FIXTURES_DIR",
    "ObjectDict",
    "OpenCodeAdapter",
    "Path",
    "PlatformAdapter",
    "RuleFinding",
    "Severity",
    "_RESOURCES_DIR",
    "config_with_enabled_rules",
    "load_platform_fixture",
    "repo_with_quality_gate",
    "cast",
    "engine_module",
    "evaluate_payload",
    "get_adapter",
    "json",
    "object_dict",
    "pytest",
    "rendered_string",
    "require_nested",
    "require_rendered",
    "require_spec",
    "string_value",
    "support",
)
