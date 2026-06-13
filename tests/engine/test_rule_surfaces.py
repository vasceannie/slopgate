from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from slopgate._types import ObjectDict, object_dict
from tests.engine.support import (
    evaluate_pretool_bash,
    write_config_from_defaults,
    write_slopgate,
)

SURFACE_RULE_ID = "CUSTOM-SURFACE-001"


def _add_surface_regex_rule(defaults: ObjectDict) -> None:
    defaults["regex_rules"] = [
        {
            "rule_id": SURFACE_RULE_ID,
            "title": "Surface runtime rule",
            "severity": "MEDIUM",
            "events": ["PreToolUse"],
            "target": "command",
            "patterns": ["surface-trigger"],
            "action": "deny",
            "message": "surface matched",
        }
    ]


def test_rule_surface_action_overrides_runtime_finding_decision(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = write_slopgate(tmp_path / "repo")

    def mutate(defaults: ObjectDict) -> None:
        _add_surface_regex_rule(defaults)
        defaults["rule_surfaces"] = {SURFACE_RULE_ID: {"hook": {"action": "ask"}}}

    write_config_from_defaults(tmp_path, monkeypatch, mutate)

    result = evaluate_pretool_bash(repo, "echo surface-trigger")
    finding = next(
        (item for item in result.findings if item.rule_id == SURFACE_RULE_ID),
        None,
    )

    assert finding is not None, "Expected custom regex rule to emit a finding"
    assert finding.decision == "ask", "Expected rule surface action to rewrite deny"
    assert object_dict(finding.metadata).get("surface_action") == "ask", (
        "Expected surface action provenance to be retained on finding metadata"
    )


def test_rule_surface_events_filter_runtime_evaluation(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = write_slopgate(tmp_path / "repo")

    def mutate(defaults: ObjectDict) -> None:
        _add_surface_regex_rule(defaults)
        defaults["rule_surfaces"] = {
            SURFACE_RULE_ID: {"hook": {"events": ["PostToolUse"]}}
        }

    write_config_from_defaults(tmp_path, monkeypatch, mutate)

    result = evaluate_pretool_bash(repo, "echo surface-trigger")

    assert all(item.rule_id != SURFACE_RULE_ID for item in result.findings), (
        "Expected hook event surface filter to skip the PreToolUse evaluation"
    )
