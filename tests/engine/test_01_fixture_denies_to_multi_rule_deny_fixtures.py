from __future__ import annotations

from tests.test_engine import (
    LoadFixture,
    assert_denied_by,
    evaluate_payload,
    finding_ids,
    hook_output,
    pytest,
    required_string,
)

@pytest.mark.parametrize(
    "fixture_name, rule_id, msg_fragment",
    [
        # BUILTIN-ENFORCE-FULL-READ is disabled in default config
        # ("pretool_read_partial.json", "BUILTIN-ENFORCE-FULL-READ", "in full first"),
        ("pretool_git_no_verify.json", "GIT-001", "hook bypass detected"),
        ("pretool_python_any.json", "PY-TYPE-001", "Any"),
        ("pretool_ts_ignore.json", "TS-LINT-002", "suppression"),
        ("pretool_rust_unwrap.json", "RS-QUALITY-002", "unwrap"),
        ("pretool_python_source_bash.json", "PY-SHELL-001", "shell edit"),
        ("pretool_datetime_fallback.json", "PY-QUALITY-004", "datetime.now"),
        ("pretool_silent_none.json", "PY-QUALITY-006", "None"),
        ("pretool_silent_except.json", "PY-EXC-002", "silent"),
        ("pretool_assertion_roulette.json", "PY-TEST-001", "assert"),
        ("pretool_python_todo.json", "PY-QUALITY-007", "TODO"),
        ("pretool_test_sleep.json", "PY-TEST-002", "sleep"),
        ("pretool_linter_config.json", "PY-LINTER-001", ""),
        ("pretool_ts_todo.json", "TS-QUALITY-003", "TODO"),
        ("pretool_test_loop_assert.json", "PY-TEST-003", ""),
        ("pretool_fixture_outside_conftest.json", "PY-TEST-004", "conftest"),
    ],
    ids=lambda p: p if isinstance(p, str) and p.endswith(".json") else "",
)
def test_fixture_denies(
    load_fixture: LoadFixture, fixture_name: str, rule_id: str, msg_fragment: str
) -> None:
    """Parametrised: each fixture must trigger its expected rule."""
    result = evaluate_payload(load_fixture(fixture_name))
    assert_denied_by(result, rule_id, msg_fragment)
    assert rule_id in finding_ids(result), (
        f"fixture {fixture_name} should trigger expected rule {rule_id}"
    )

class TestMultiRuleDenyFixtures:
    def test_default_swallow(self, load_fixture: LoadFixture) -> None:
        """PY-EXC-001 or PY-QUALITY-005 may fire on log+return-default."""
        result = evaluate_payload(load_fixture("pretool_default_swallow.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "PY-QUALITY-005" in reason or "PY-EXC-001" in reason

    def test_fe_linter(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_fe_linter.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "FE-LINTER-001" in reason or "BUILTIN-PROTECTED-PATHS" in reason

    def test_design_tokens(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_design_tokens.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "STYLE-004" in reason or "STYLE-005" in reason

    def test_shell_bypass(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_shell_bypass.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "SHELL-001" in reason or "GLOBAL-BUILTIN-SYSTEM-PROTECTION" in reason

    def test_quality_test_path(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_quality_test_path.json"))
        reason = required_string(hook_output(result), "permissionDecisionReason")
        assert "QA-PATH-003" in reason or "BUILTIN-PROTECTED-PATHS" in reason
