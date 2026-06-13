from __future__ import annotations

import json
import os
import re
import string
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st
import pytest

from slopgate.lint._collectors import run_all_collectors
from slopgate.lint._config import load_config, reset_config
from slopgate.lint._helpers import parse_files
from slopgate.lint._regex_rules import regex_rule_collectors
from slopgate.models import RegexRuleConfig
from slopgate.rules.regex_rule_matching import (
    RegexRuleMatcher,
    compile_regex_patterns,
)

LONG_LINE_PAYLOAD_LENGTH = 140
CLI_RULE_UNDER_TEST = "long-line"
HOOK_RULE_UNDER_TEST = "PY-CODE-010"
TOKEN_ALPHABET = string.ascii_letters + string.digits + "_"
PROPERTY_TEST_EXAMPLES = 20


def _write_project_source(project_root: Path) -> Path:
    src_dir = project_root / "src"
    src_dir.mkdir(exist_ok=True)
    source_file = src_dir / "app.py"
    source_file.write_text(
        "VALUE = '" + ("x" * LONG_LINE_PAYLOAD_LENGTH) + "'\n",
        encoding="utf-8",
    )
    return source_file


def _collector_names(project_root: Path, source_file: Path) -> set[str]:
    load_config(project_root)
    return {name for name, _violations in run_all_collectors([source_file], [])}


def _collector_names_with_disabled_rule(
    project_root: Path,
    source_file: Path,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> set[str]:
    global_config = config_dir / "config.json"
    global_config.write_text(
        json.dumps({"enabled_cli_rules": {CLI_RULE_UNDER_TEST: False}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLOPGATE_CONFIG", str(global_config))
    reset_config()
    return _collector_names(project_root, source_file)


def _collector_names_with_surface_disabled_rule(
    project_root: Path,
    source_file: Path,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> set[str]:
    global_config = config_dir / "config.json"
    global_config.write_text(
        json.dumps(
            {"rule_surfaces": {HOOK_RULE_UNDER_TEST: {"cli": {"enabled": False}}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLOPGATE_CONFIG", str(global_config))
    reset_config()
    return _collector_names(project_root, source_file)


def _collector_map(project_root: Path, source_file: Path) -> dict[str, int]:
    load_config(project_root)
    return {
        name: len(violations)
        for name, violations in run_all_collectors([source_file], [])
    }


def _write_global_config(
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    global_config = config_dir / "config.json"
    global_config.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(global_config))
    reset_config()


def _regex_rule_payload(rule_id: str, *, target: str) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "title": "Ban sample token",
        "severity": "HIGH",
        "events": ["PreToolUse"],
        "target": target,
        "patterns": ["forbidden_token"],
        "message": "{rule_id}:{path}",
        "action": "deny",
    }


def _property_regex_rule_config(rule_id: str, token: str) -> dict[str, object]:
    return {
        "regex_rules": [
            {
                **_regex_rule_payload(rule_id, target="content"),
                "patterns": [re.escape(token)],
            }
        ],
        "rule_surfaces": {rule_id: {"cli": {"enabled": True}}},
    }


def _collect_enabled_regex_token_violations(token: str) -> int:
    rule_id = "CUSTOM-CONTENT-PROPERTY-001"
    with tempfile.TemporaryDirectory() as project_raw:
        with tempfile.TemporaryDirectory() as config_raw:
            project_root = Path(project_raw)
            source_file = project_root / "src" / f"app_{token}.py"
            source_file.parent.mkdir(exist_ok=True)
            source_file.write_text(f"VALUE = {token!r}\n", encoding="utf-8")
            config_path = Path(config_raw) / "config.json"
            config_path.write_text(
                json.dumps(_property_regex_rule_config(rule_id, token)),
                encoding="utf-8",
            )
            return _collect_with_config_path(project_root, source_file, config_path)[
                rule_id
            ]


def _collect_with_config_path(
    project_root: Path,
    source_file: Path,
    config_path: Path,
) -> dict[str, int]:
    previous_config = os.environ.get("SLOPGATE_CONFIG")
    os.environ["SLOPGATE_CONFIG"] = str(config_path)
    reset_config()
    try:
        load_config(project_root)
        collectors = regex_rule_collectors(parse_files([source_file]), [])
        return {name: len(violations) for name, violations in collectors}
    finally:
        if previous_config is None:
            os.environ.pop("SLOPGATE_CONFIG", None)
        else:
            os.environ["SLOPGATE_CONFIG"] = previous_config
        reset_config()


def test_enabled_cli_rules_removes_disabled_collectors_from_lint_registry(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = _write_project_source(tmp_project)

    reset_config()
    enabled_names = _collector_names(tmp_project, source_file)
    disabled_names = _collector_names_with_disabled_rule(
        tmp_project, source_file, tmp_path, monkeypatch
    )

    assert CLI_RULE_UNDER_TEST in enabled_names, (
        "Expected long-line collector to be registered before config disablement"
    )
    assert CLI_RULE_UNDER_TEST not in disabled_names, (
        "Expected enabled_cli_rules=false to remove the collector from lint output"
    )


def test_rule_surface_cli_enablement_removes_mapped_collectors_from_lint_registry(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = _write_project_source(tmp_project)

    reset_config()
    enabled_names = _collector_names(tmp_project, source_file)
    disabled_names = _collector_names_with_surface_disabled_rule(
        tmp_project, source_file, tmp_path, monkeypatch
    )

    assert CLI_RULE_UNDER_TEST in enabled_names, (
        "Expected long-line collector to be registered before surface disablement"
    )
    assert CLI_RULE_UNDER_TEST not in disabled_names, (
        "Expected PY-CODE-010 cli surface=false to remove the mapped collector"
    )


def test_rule_surface_cli_enablement_runs_content_regex_rule_as_lint_collector(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = tmp_project / "src" / "app.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text("VALUE = 'forbidden_token'\n", encoding="utf-8")
    rule_id = "CUSTOM-CONTENT-001"
    _write_global_config(
        tmp_path,
        monkeypatch,
        {
            "regex_rules": [_regex_rule_payload(rule_id, target="content")],
            "rule_surfaces": {rule_id: {"cli": {"enabled": True}}},
        },
    )

    collectors = _collector_map(tmp_project, source_file)

    assert collectors[rule_id] == 1


def test_regex_rule_collectors_directly_exposes_content_rule_violations(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = tmp_project / "src" / "app.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text("VALUE = 'forbidden_token'\n", encoding="utf-8")
    rule_id = "CUSTOM-CONTENT-DIRECT-001"
    _write_global_config(
        tmp_path,
        monkeypatch,
        {
            "regex_rules": [_regex_rule_payload(rule_id, target="content")],
            "rule_surfaces": {rule_id: {"cli": {"enabled": True}}},
        },
    )
    load_config(tmp_project)

    collectors = dict(regex_rule_collectors(parse_files([source_file]), []))

    assert collectors[rule_id][0].relative_path == "src/app.py"


def test_regex_rule_matcher_uses_compiled_patterns_and_path_filters() -> None:
    config = RegexRuleConfig(
        rule_id="CUSTOM-MATCHER-001",
        title="Matcher path filter",
        target="content",
        patterns=["forbidden_token"],
        path_globs=["src/**"],
        exclude_path_globs=["src/generated/**"],
    )
    matcher = RegexRuleMatcher(config=config, patterns=compile_regex_patterns(config))

    assert matcher.path_hit("src/app.py", "FORBIDDEN_TOKEN") is not None, (
        "compiled matcher should apply case-insensitive regex rule flags"
    )
    assert matcher.path_hit("src/generated/app.py", "forbidden_token") is None, (
        "compiled matcher should preserve regex rule exclude globs"
    )


@settings(max_examples=PROPERTY_TEST_EXAMPLES)
@given(token=st.text(alphabet=TOKEN_ALPHABET, min_size=1, max_size=24))
def test_regex_rule_collectors_reports_enabled_content_rule_for_any_token(
    token: str,
) -> None:
    assert _collect_enabled_regex_token_violations(token) == 1, (
        "enabled content regex rules should report one matching file violation"
    )


def test_rule_surface_cli_enablement_runs_path_regex_rule_as_lint_collector(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = tmp_project / "src" / "forbidden_token.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text("VALUE = 1\n", encoding="utf-8")
    rule_id = "CUSTOM-PATH-001"
    _write_global_config(
        tmp_path,
        monkeypatch,
        {
            "regex_rules": [_regex_rule_payload(rule_id, target="path")],
            "rule_surfaces": {rule_id: {"cli": {"enabled": True}}},
        },
    )

    collectors = _collector_map(tmp_project, source_file)

    assert collectors[rule_id] == 1


def test_regex_rule_without_cli_surface_does_not_become_lint_collector(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = tmp_project / "src" / "app.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text("VALUE = 'forbidden_token'\n", encoding="utf-8")
    rule_id = "CUSTOM-DISABLED-001"
    _write_global_config(
        tmp_path,
        monkeypatch,
        {"regex_rules": [_regex_rule_payload(rule_id, target="content")]},
    )

    collectors = _collector_map(tmp_project, source_file)

    assert rule_id not in collectors


def test_command_regex_rule_is_not_exposed_as_batch_lint_collector(
    tmp_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = tmp_project / "src" / "app.py"
    source_file.parent.mkdir(exist_ok=True)
    source_file.write_text("VALUE = 'forbidden_token'\n", encoding="utf-8")
    rule_id = "CUSTOM-COMMAND-001"
    _write_global_config(
        tmp_path,
        monkeypatch,
        {
            "regex_rules": [_regex_rule_payload(rule_id, target="command")],
            "rule_surfaces": {rule_id: {"cli": {"enabled": True}}},
        },
    )

    collectors = _collector_map(tmp_project, source_file)

    assert rule_id not in collectors

