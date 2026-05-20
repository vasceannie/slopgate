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

from vibeforcer.engine import _render as engine_module

import pytest

from tests import support as test_support

from vibeforcer._types import ObjectDict, object_dict, string_value
from vibeforcer.adapters import get_adapter, ADAPTERS
from vibeforcer.adapters.base import PlatformAdapter
from vibeforcer.adapters.claude import ClaudeAdapter
from vibeforcer.adapters.codex import CodexAdapter
from vibeforcer.adapters.opencode import OpenCodeAdapter
from vibeforcer.engine import evaluate_payload
from vibeforcer.models import RuleFinding, Severity

FIXTURES_DIR = test_support.BUNDLE_ROOT / "fixtures"
_RESOURCES_DIR = test_support.BUNDLE_ROOT / "src" / "vibeforcer" / "resources"


def _load_platform_fixture(platform: str, fixture_name: str) -> ObjectDict:
    fixture_path = FIXTURES_DIR / platform / fixture_name
    return object_dict(cast(object, json.loads(fixture_path.read_text())))


def _repo_with_quality_gate(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n",
        encoding="utf-8",
    )
    return repo


def _config_with_enabled_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *rule_ids: str
) -> None:
    raw = json.loads((_RESOURCES_DIR / "defaults.json").read_text(encoding="utf-8"))
    enabled = dict(raw.get("enabled_rules", {}))
    for rule_id in rule_ids:
        enabled[rule_id] = True
    raw["enabled_rules"] = enabled
    config_path = tmp_path / "adapter-spec-config.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("VIBEFORCER_CONFIG", str(config_path))


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


# ===========================================================================
# Adapter registry
# ===========================================================================


# ===========================================================================
# Claude adapter — backward compatibility
# ===========================================================================


# ===========================================================================
# Codex adapter
# ===========================================================================


# ===========================================================================
# OpenCode adapter
# ===========================================================================


# ===========================================================================
# Base adapter helpers
# ===========================================================================


# ===========================================================================
# Multi-finding edge cases (cross-adapter)
# ===========================================================================


# ===========================================================================
# Fixture replay — full engine pipeline
# ===========================================================================


# ===========================================================================
# Cross-platform: same findings, different output shapes
# ===========================================================================


# ===========================================================================
# CLI --platform integration
# ===========================================================================

# Exported test support used by split test modules.
__all__ = ('ADAPTERS', 'Callable', 'ClaudeAdapter', 'CodexAdapter', 'FIXTURES_DIR', 'ObjectDict', 'OpenCodeAdapter', 'Path', 'PlatformAdapter', 'RuleFinding', 'Severity', '_RESOURCES_DIR', '_config_with_enabled_rules', '_load_platform_fixture', '_repo_with_quality_gate', 'cast', 'engine_module', 'evaluate_payload', 'get_adapter', 'json', 'object_dict', 'pytest', 'rendered_string', 'require_nested', 'require_rendered', 'require_spec', 'string_value', 'test_support')
