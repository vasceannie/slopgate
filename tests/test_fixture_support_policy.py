"""Fixture support-module policy for lint and runtime hooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibeforcer.engine import evaluate_payload
from vibeforcer.lint._config import load_config, reset_config
from vibeforcer.lint._detectors.test_smells import detect_fixtures_outside_conftest
from vibeforcer.lint._helpers import find_source_files, parse_files
from vibeforcer.policy_defaults import LINT_PATH_DEFAULTS

from tests import support as test_support


_FIXTURE_CODE = """import pytest

@pytest.fixture
def client():
    return object()
"""


_TEST_FIXTURE_CODE = f"""{_FIXTURE_CODE}

def test_uses_client(client):
    assert client is not None
"""


def _write_project_file(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_default_lint_excludes_include_common_virtualenv_dirs() -> None:
    exclude_dirs = LINT_PATH_DEFAULTS["exclude_dirs"]

    assert ".venv" in exclude_dirs
    assert "venv" in exclude_dirs
    assert "env" in exclude_dirs


def test_quality_gate_template_excludes_common_virtualenv_dirs() -> None:
    template_path = (
        Path(__file__).parents[1]
        / "src"
        / "vibeforcer"
        / "resources"
        / "quality_gate_template.toml"
    )
    template = template_path.read_text(encoding="utf-8")

    assert 'exclude_dirs = [".venv", "venv", "env",' in template


def test_linter_file_discovery_skips_common_virtualenv_dirs(tmp_path: Path) -> None:
    load_config(tmp_path)
    try:
        source_file = _write_project_file(tmp_path, "src/app.py", "x = 1\n")
        _ = _write_project_file(tmp_path, "src/.venv/lib/nope.py", "x = 1\n")
        _ = _write_project_file(tmp_path, "src/venv/lib/nope.py", "x = 1\n")
        _ = _write_project_file(tmp_path, "src/env/lib/nope.py", "x = 1\n")
        _ = _write_project_file(tmp_path, "src/environment/app.py", "x = 1\n")

        discovered = {path.relative_to(tmp_path).as_posix() for path in find_source_files()}

        assert source_file.relative_to(tmp_path).as_posix() in discovered
        assert "src/environment/app.py" in discovered
        assert "src/.venv/lib/nope.py" not in discovered
        assert "src/venv/lib/nope.py" not in discovered
        assert "src/env/lib/nope.py" not in discovered
    finally:
        reset_config()


@pytest.mark.parametrize(
    "relative_path",
    [
        pytest.param("tests/unit/_fixtures/app.py", id="area-fixtures-dir"),
        pytest.param("tests/unit/support/app.py", id="area-support-dir"),
    ],
)
def test_linter_allows_dedicated_fixture_support_modules(
    tmp_path: Path,
    relative_path: str,
) -> None:
    load_config(tmp_path)
    try:
        fixture_module = _write_project_file(tmp_path, relative_path, _FIXTURE_CODE)
        parsed = parse_files([fixture_module])

        violations = detect_fixtures_outside_conftest(parsed)

        assert violations == []
    finally:
        reset_config()


def test_linter_still_blocks_inline_test_module_fixtures(tmp_path: Path) -> None:
    load_config(tmp_path)
    try:
        test_module = _write_project_file(
            tmp_path,
            "tests/unit/test_app.py",
            _TEST_FIXTURE_CODE,
        )
        parsed = parse_files([test_module])

        violations = detect_fixtures_outside_conftest(parsed)

        assert [violation.rule for violation in violations] == ["fixture-outside-conftest"]
        assert violations[0].identifier == "client"
    finally:
        reset_config()


def test_hook_allows_fixture_support_module_write(tmp_project: Path) -> None:
    payload = {
        "session_id": "fixture-support-policy",
        "cwd": str(tmp_project),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "tests/unit/_fixtures/app.py",
            "content": _FIXTURE_CODE,
        },
    }

    result = evaluate_payload(payload)

    assert "PY-TEST-004" not in test_support.finding_ids(result)


def test_hook_fixture_denial_mentions_support_modules(tmp_project: Path) -> None:
    payload = {
        "session_id": "fixture-support-policy",
        "cwd": str(tmp_project),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "tests/unit/test_app.py",
            "content": _TEST_FIXTURE_CODE,
        },
    }

    result = evaluate_payload(payload)

    test_support.assert_denied_by(result, "PY-TEST-004")
    reason = test_support.required_string(
        test_support.hook_output(result), "permissionDecisionReason"
    )
    assert "support" in reason.lower() or "_fixtures" in reason.lower(), (
        "fixture denial should steer agents toward conftest-backed support modules: "
        f"{reason}"
    )


def test_hook_fixture_rule_config_keeps_support_modules_out_of_block_globs(
    bundle_root: Path,
) -> None:
    raw_config = json.loads(
        (bundle_root / "src" / "vibeforcer" / "resources" / "defaults.json").read_text(
            encoding="utf-8"
        )
    )
    fixture_rule = next(
        rule
        for rule in raw_config["regex_rules"]
        if rule.get("rule_id") == "PY-TEST-004"
    )

    joined_globs = "\n".join(fixture_rule.get("path_globs", []))
    assert "_fixtures" not in joined_globs
    assert "support" not in joined_globs
    assert "test_*.py" in joined_globs
    assert "support" in fixture_rule["message"].lower()
