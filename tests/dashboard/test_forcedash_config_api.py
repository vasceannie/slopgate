from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import cast

from slopgate._types import object_dict

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SRC_DIR))

_config_api = importlib.import_module("forcedash_server.config_api")

apply_config_patch = _config_api.apply_config_patch
dashboard_config = _config_api.dashboard_config
parse_config_payload = _config_api.parse_config_payload

SURFACE_LIVE: dict[str, object] = {
    "rule_surfaces": {
        "PY-LOG-001": {
            "hook": {"enabled": True, "events": ["PreToolUse"]},
            "cli": {"enabled": True},
        }
    }
}

SURFACE_PATCH: dict[str, object] = {
    "rule_surfaces": {
        "PY-LOG-001": {
            "hook": {
                "enabled": False,
                "events": ["PostToolUse", 1],
                "action": "ask",
            },
            "cli": {"enabled": False},
        },
        "PY-LOG-002": {"hook": {"action": "invalid", "events": ["Stop"]}},
    }
}

SURFACE_EXPECTED: dict[str, object] = {
    "PY-LOG-001": {
        "hook": {
            "enabled": False,
            "events": ["PostToolUse"],
            "action": "ask",
        },
        "cli": {"enabled": False},
    },
    "PY-LOG-002": {"hook": {"events": ["Stop"]}},
}


def test_apply_config_patch_preserves_unmentioned_legacy_config_fields() -> None:
    live: dict[str, object] = {
        "enabled_rules": {"PY-LOG-002": False, "SHELL-001": True},
        "enabled_cli_rules": {"long-method": False, "long-line": True},
        "regex_rules": [{"id": "keep"}],
        "skip_paths": ["old"],
        "unrelated": {"kept": True},
    }

    result = apply_config_patch(
        live,
        {
            "enabled_rules": {"PY-LOG-002": True, "ignored": "yes"},
            "enabled_cli_rules": {"long-method": True, "ignored": "yes"},
            "skip_paths": ["new", 123],
        },
    )

    assert result["enabled_rules"] == {
        "PY-LOG-002": True,
        "SHELL-001": True,
    }, "Expected boolean rule patching to merge valid booleans only"
    assert result["enabled_cli_rules"] == {"long-method": True, "long-line": True}, (
        "Expected CLI collector patching to merge valid booleans only"
    )
    assert result["regex_rules"] == [{"id": "keep"}], (
        "Expected omitted regex rules to remain unchanged"
    )
    assert result["skip_paths"] == ["new"], (
        "Expected skip path patching to keep string paths only"
    )
    assert result["unrelated"] == {"kept": True}, (
        "Expected unrelated config fields to be preserved"
    )


def test_apply_config_patch_merges_sanitized_rule_surfaces() -> None:
    result = apply_config_patch(SURFACE_LIVE, SURFACE_PATCH)

    assert result["rule_surfaces"] == SURFACE_EXPECTED, (
        "Expected rule surface patching to merge sanitized hook and CLI sections"
    )


def test_parse_config_payload_rejects_non_object_json() -> None:
    config, error = parse_config_payload("[]")

    assert config == {}, "Expected invalid config payload to return an empty config"
    assert error == "Config payload must be a JSON object", (
        "Expected a semantic error for non-object config"
    )


def test_dashboard_config_adds_rule_counterpart_metadata() -> None:
    config = dashboard_config({"enabled_rules": {}})

    counterparts_obj = config.get("rule_counterparts")
    assert isinstance(counterparts_obj, dict), (
        "Expected dashboard config to include rule counterpart metadata"
    )
    counterparts = object_dict(cast(object, counterparts_obj))
    assert counterparts.get("PY-CODE-010") == ["long-line"], (
        "Expected dashboard counterparts to come from Slopgate parity metadata"
    )
