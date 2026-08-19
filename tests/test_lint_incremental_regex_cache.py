from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.lint._collectors import CollectorRunOptions, run_all_collectors
from slopgate.lint._config import load_config, reset_config, set_config

RULE_ID = "CUSTOM-CACHE-001"


def _write_runtime_config(path: Path, *, excluded: bool = False) -> None:
    rule = {
        "rule_id": RULE_ID,
        "title": "Ban cached token",
        "severity": "HIGH",
        "events": ["PreToolUse"],
        "target": "content",
        "patterns": ["forbidden_token"],
        "exclude_path_globs": ["src/**"] if excluded else [],
        "message": "{rule_id}:{path}",
        "action": "deny",
    }
    path.write_text(
        json.dumps(
            {
                "regex_rules": [rule],
                "rule_surfaces": {RULE_ID: {"cli": {"enabled": True}}},
            }
        ),
        encoding="utf-8",
    )


def _configured_project(
    root: Path, config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    source = root / "src/app.py"
    source.parent.mkdir()
    source.write_text("VALUE = 'forbidden_token'\n", encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    set_config(load_config(root))
    return source


def _run_cached(source: Path, *, use_index: bool = True) -> dict[str, int]:
    options = CollectorRunOptions(persist_index=use_index, use_index=use_index)
    return {
        collector_id: len(violations)
        for collector_id, violations in run_all_collectors([source], [], options)
    }


def _regex_cache_contract(
    root: Path,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    exclude_on_second_run: bool,
) -> tuple[int, int, int]:
    _write_runtime_config(config_path)
    source = _configured_project(root, config_path, monkeypatch)
    first = _run_cached(source)[RULE_ID]
    if exclude_on_second_run:
        _write_runtime_config(config_path, excluded=True)
        set_config(load_config(root))
    second = _run_cached(source).get(RULE_ID, 0)
    reference = _run_cached(source, use_index=False).get(RULE_ID, 0)
    reset_config()
    return first, second, reference


def test_warm_clean_cache_preserves_custom_regex_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _regex_cache_contract(
        tmp_path,
        tmp_path / "config.json",
        monkeypatch,
        exclude_on_second_run=False,
    ) == (1, 1, 1)


def test_regex_exclusion_change_invalidates_warm_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _regex_cache_contract(
        tmp_path,
        tmp_path / "config.json",
        monkeypatch,
        exclude_on_second_run=True,
    ) == (1, 0, 0)
