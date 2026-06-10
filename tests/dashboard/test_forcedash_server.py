from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SRC_DIR))

from forcedash_server.config_api import apply_config_patch, parse_config_payload
from forcedash_server.harness import parse_harness_payload
from forcedash_server.snapshot import (
    build_trace_snapshot_script,
    parse_snapshot_payload,
    snapshot_lookback_hours,
)

PayloadParser = Callable[[str], tuple[dict[str, object], str | None]]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/snapshot", 168),
        ("/api/snapshot?lookback_hours=2", 2),
        ("/api/snapshot?hours=9999", 720),
        ("/api/snapshot?hours=bad", 168),
        ("/api/snapshot?hours=0", 1),
    ],
)
def test_snapshot_lookback_hours_clamps_query_values(path: str, expected: int) -> None:
    assert snapshot_lookback_hours(path) == expected, (
        f"Expected {path} to resolve to {expected} hours"
    )


def test_apply_config_patch_preserves_unmentioned_config_fields() -> None:
    live: dict[str, object] = {
        "enabled_rules": {"PY-LOG-002": False, "SHELL-001": True},
        "regex_rules": [{"id": "keep"}],
        "skip_paths": ["old"],
        "unrelated": {"kept": True},
    }
    patch: dict[str, object] = {
        "enabled_rules": {"PY-LOG-002": True, "ignored": "yes"},
        "skip_paths": ["new", 123],
    }

    result = apply_config_patch(live, patch)

    assert result["enabled_rules"] == {
        "PY-LOG-002": True,
        "SHELL-001": True,
    }, "Expected boolean rule patching to merge valid booleans only"
    assert result["regex_rules"] == [{"id": "keep"}], (
        "Expected omitted regex rules to remain unchanged"
    )
    assert result["skip_paths"] == ["new"], (
        "Expected skip path patching to keep string paths only"
    )
    assert result["unrelated"] == {"kept": True}, (
        "Expected unrelated config fields to be preserved"
    )


def test_parse_config_payload_rejects_non_object_json() -> None:
    config, error = parse_config_payload("[]")

    assert config == {}, "Expected invalid config payload to return an empty config"
    assert error == "Config payload must be a JSON object", (
        "Expected a semantic error for non-object config"
    )


@pytest.mark.parametrize(
    ("parser", "error_text"),
    [
        (parse_harness_payload, "Harness status payload must be a JSON object"),
        (parse_snapshot_payload, "Snapshot payload must be a JSON object"),
    ],
)
def test_remote_payload_parsers_reject_non_object_json(
    parser: PayloadParser, error_text: str
) -> None:
    payload, error = parser("[]")

    assert payload == {}, "Expected invalid remote payload to return an empty object"
    assert error == error_text, "Expected parser-specific non-object error text"


def test_build_trace_snapshot_script_substitutes_runtime_tokens() -> None:
    script = build_trace_snapshot_script(42)

    assert "LOOKBACK_HOURS = 42" in script, "Expected lookback token to be replaced"
    assert "__LOOKBACK_HOURS__" not in script, "Expected no unresolved lookback token"
    assert "__SSH_HOST__" not in script, "Expected no unresolved SSH host token"
