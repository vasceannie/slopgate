from __future__ import annotations

from tests.test_adapters import (
    FIXTURES_DIR,
    Path,
    _load_platform_fixture,
    _repo_with_quality_gate,
    cast,
    evaluate_payload,
    json,
    object_dict,
    pytest,
    require_spec,
    test_support,
)

class TestFixtureReplay:
    """Load real fixtures and replay them through the engine.

    These are integration tests: fixture → normalize → rules → render → verify.
    No mocking. Verifies that the full pipeline produces sensible output.
    """

    def test_codex_git_no_verify_denied(self, tmp_path: Path) -> None:
        payload = _load_platform_fixture("codex", "pretool_bash_git_no_verify.json")
        repo = _repo_with_quality_gate(tmp_path)
        payload["cwd"] = str(repo)
        result = evaluate_payload(payload, platform="codex")
        assert result.output is not None
        spec = require_spec(test_support.require_output(result))
        assert test_support.output_string(spec, "permissionDecision") == "deny"
        assert "GIT-001" in test_support.output_string(spec, "permissionDecisionReason")
        # Also verify findings list
        ids = {f.rule_id for f in result.findings}
        assert "GIT-001" in ids

    def test_codex_rm_rf_denied(self) -> None:
        payload = _load_platform_fixture("codex", "pretool_bash_rm_rf.json")
        result = evaluate_payload(payload, platform="codex")
        spec = require_spec(test_support.require_output(result))
        assert test_support.output_string(spec, "permissionDecision") == "deny"

    def test_codex_session_start_produces_context(self) -> None:
        payload = object_dict(
            cast(
                object,
                json.loads((FIXTURES_DIR / "codex" / "session_start.json").read_text()),
            )
        )
        result = evaluate_payload(payload, platform="codex")
        # SessionStart may or may not produce output depending on config;
        # the key is it doesn't crash and returns a valid EngineResult
        assert result.event_name == "SessionStart"
        assert result.errors == []

    def test_opencode_git_no_verify_denied(self, tmp_path: Path) -> None:
        payload = _load_platform_fixture("opencode", "pretool_bash_git_no_verify.json")
        repo = _repo_with_quality_gate(tmp_path)
        payload["cwd"] = str(repo)
        result = evaluate_payload(payload, platform="opencode")
        assert result.output is not None
        rendered = test_support.require_output(result)
        assert rendered["action"] == "block"
        assert "GIT-001" in test_support.required_string(rendered, "reason")

    def test_opencode_write_protected_denied(self) -> None:
        payload = object_dict(
            cast(
                object,
                json.loads(
                    (
                        FIXTURES_DIR / "opencode" / "pretool_write_protected.json"
                    ).read_text()
                ),
            )
        )
        result = evaluate_payload(payload, platform="opencode")
        assert result.output is not None
        assert result.output["action"] == "block"
        # Protected path rule should fire
        ids = {f.rule_id for f in result.findings}
        assert any(
            "PROTECT" in rid or "CUPCAKE" in rid or "SECURITY" in rid for rid in ids
        ), f"Expected a protection rule, got: {ids}"

    def test_opencode_session_idle_no_crash(self) -> None:
        payload = object_dict(
            cast(
                object,
                json.loads(
                    (FIXTURES_DIR / "opencode" / "session_idle.json").read_text()
                ),
            )
        )
        result = evaluate_payload(payload, platform="opencode")
        assert result.event_name == "Stop"
        assert result.errors == []

    def test_opencode_permission_asked_processes(self) -> None:
        payload = object_dict(
            cast(
                object,
                json.loads(
                    (FIXTURES_DIR / "opencode" / "permission_asked.json").read_text()
                ),
            )
        )
        result = evaluate_payload(payload, platform="opencode")
        assert result.event_name == "PermissionRequest"
        assert result.errors == []
        assert result.output is not None, (
            "permission_asked fixture should produce output"
        )
        assert test_support.require_output(result)["action"] == "block"

    def test_codex_posttool_no_crash(self) -> None:
        payload = object_dict(
            cast(
                object,
                json.loads((FIXTURES_DIR / "codex" / "posttool_bash.json").read_text()),
            )
        )
        result = evaluate_payload(payload, platform="codex")
        assert result.event_name == "PostToolUse"
        assert result.errors == []

    @pytest.mark.parametrize(
        "fixture_rel,platform",
        [
            # codex sub-fixtures
            ("codex/posttool_bash.json", "codex"),
            ("codex/pretool_bash_git_no_verify.json", "codex"),
            ("codex/pretool_bash_rm_rf.json", "codex"),
            ("codex/session_start.json", "codex"),
            ("codex/stop_basic.json", "codex"),
            ("codex/user_prompt_submit.json", "codex"),
            # opencode sub-fixtures
            ("opencode/permission_asked.json", "opencode"),
            ("opencode/pretool_bash_git_no_verify.json", "opencode"),
            ("opencode/pretool_edit_python_todo.json", "opencode"),
            ("opencode/pretool_write_protected.json", "opencode"),
            ("opencode/session_idle.json", "opencode"),
            # top-level claude fixtures
            ("configchange_disable_hooks.json", "claude"),
            ("configchange_safe.json", "claude"),
            ("pretool_assertion_roulette.json", "claude"),
            ("pretool_baseline_inflate.json", "claude"),
            ("pretool_datetime_fallback.json", "claude"),
            ("pretool_default_swallow.json", "claude"),
            ("pretool_design_tokens.json", "claude"),
            ("pretool_fe_linter.json", "claude"),
            ("pretool_fixture_outside_conftest.json", "claude"),
            ("pretool_git_no_verify.json", "claude"),
            ("pretool_git_stash.json", "claude"),
            ("pretool_linter_config.json", "claude"),
            ("pretool_python_any.json", "claude"),
            ("pretool_python_source_bash.json", "claude"),
            ("pretool_python_todo.json", "claude"),
            ("pretool_quality_test_path.json", "claude"),
            ("pretool_read_partial.json", "claude"),
            ("pretool_rust_unwrap.json", "claude"),
            ("pretool_shell_bypass.json", "claude"),
            ("pretool_silent_except.json", "claude"),
            ("pretool_silent_none.json", "claude"),
            ("pretool_test_loop_assert.json", "claude"),
            ("pretool_test_sleep.json", "claude"),
            ("pretool_ts_ignore.json", "claude"),
            ("pretool_ts_todo.json", "claude"),
            ("sessionstart_startup.json", "claude"),
            ("stop_preexisting.json", "claude"),
        ],
    )
    def test_all_fixtures_replay_without_errors(
        self, fixture_rel: str, platform: str
    ) -> None:
        """Every fixture file replays through the engine without errors."""
        payload = object_dict(
            cast(object, json.loads((FIXTURES_DIR / fixture_rel).read_text()))
        )
        result = evaluate_payload(payload, platform=platform)
        assert result.errors == [], (
            f"Fixture {fixture_rel} produced errors: {result.errors}"
        )
