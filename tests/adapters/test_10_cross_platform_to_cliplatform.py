from __future__ import annotations

from tests.test_adapters import (
    Path,
    _config_with_enabled_rules,
    evaluate_payload,
    object_dict,
    pytest,
    require_spec,
    string_value,
    test_support,
)

class TestCrossPlatform:
    """Same payload through all adapters produces correct per-platform output."""

    def _git_no_verify_payload(self) -> dict[str, object]:
        return {
            "session_id": "cross-test",
            "cwd": str(test_support.BUNDLE_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit --no-verify -m 'test'"},
        }

    def _permission_spec_for_platform(self, platform: str) -> dict[str, object]:
        result = evaluate_payload(self._git_no_verify_payload(), platform=platform)
        assert result.output is not None, f"{platform} should produce output"
        return require_spec(test_support.require_output(result))

    def test_claude_and_codex_produce_same_structure(self) -> None:
        """Claude and Codex both use hookSpecificOutput.permissionDecision."""
        claude_spec = self._permission_spec_for_platform("claude")
        codex_spec = self._permission_spec_for_platform("codex")
        assert test_support.output_string(claude_spec, "permissionDecision") == "deny", (
            "Claude should deny"
        )
        assert test_support.output_string(codex_spec, "permissionDecision") == "deny", (
            "Codex should deny"
        )
        assert "GIT-001" in test_support.output_string(
            claude_spec, "permissionDecisionReason"
        ), "GIT-001 should appear in Claude reason"
        assert "GIT-001" in test_support.output_string(
            codex_spec, "permissionDecisionReason"
        ), "GIT-001 should appear in Codex reason"

    def test_opencode_produces_block_action(self) -> None:
        """OpenCode uses action:block instead of hookSpecificOutput."""
        payload = self._git_no_verify_payload()
        # Simulate OpenCode shim sending us the payload with OC event name
        oc_payload = dict(payload)
        oc_payload["hook_event_name"] = "tool.execute.before"
        oc_payload["tool_name"] = "bash"  # lowercase from OpenCode

        result = evaluate_payload(oc_payload, platform="opencode")
        assert result.output is not None, "OpenCode should produce output"
        rendered = test_support.require_output(result)
        assert rendered["action"] == "block", "OpenCode should produce block action"
        assert "GIT-001" in test_support.required_string(rendered, "reason"), (
            "GIT-001 should appear in reason"
        )

    def test_same_findings_different_format(self) -> None:
        """All platforms produce the same findings, just rendered differently."""
        payload = self._git_no_verify_payload()
        claude_result = evaluate_payload(payload, platform="claude")

        oc_payload = dict(payload)
        oc_payload["hook_event_name"] = "tool.execute.before"
        oc_payload["tool_name"] = "bash"
        opencode_result = evaluate_payload(oc_payload, platform="opencode")

        codex_result = evaluate_payload(payload, platform="codex")

        # All should have the same finding rule IDs
        claude_ids = {f.rule_id for f in claude_result.findings}
        codex_ids = {f.rule_id for f in codex_result.findings}
        opencode_ids = {f.rule_id for f in opencode_result.findings}

        assert "GIT-001" in claude_ids, "Claude should find GIT-001"
        assert "GIT-001" in codex_ids, "Codex should find GIT-001"
        assert "GIT-001" in opencode_ids, "OpenCode should find GIT-001"

    @staticmethod
    def _full_read_unlock_failures(
        initial_payload: dict[str, object], follow_up_payload: dict[str, object]
    ) -> tuple[list[str], list[str]]:
        platform_results = {
            platform: (
                evaluate_payload(dict(initial_payload), platform=platform),
                evaluate_payload(dict(follow_up_payload), platform=platform),
            )
            for platform in ("claude", "codex")
        }
        dirty_initial_reads = [
            platform
            for platform, (first, _second) in platform_results.items()
            if first.findings
        ]
        denied_follow_ups = [
            platform
            for platform, (_first, second) in platform_results.items()
            if "BUILTIN-ENFORCE-FULL-READ"
            in {finding.rule_id for finding in second.findings}
        ]
        return dirty_initial_reads, denied_follow_ups

    def test_full_read_unlock_survives_relative_follow_up_for_claude_and_codex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Adapter/platform selection must not break stateful read-path normalization."""
        _config_with_enabled_rules(tmp_path, monkeypatch, "BUILTIN-ENFORCE-FULL-READ")
        target = tmp_path / "module.py"
        target.write_text("print('hi')\nprint('bye')\n", encoding="utf-8")
        initial_payload = {
            "session_id": "adapter-cross-read",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": str(target)},
        }
        follow_up_payload = {
            "session_id": "adapter-cross-read",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "module.py", "offset": 1, "limit": 1},
        }
        dirty_initial_reads, denied_follow_ups = self._full_read_unlock_failures(
            initial_payload, follow_up_payload
        )
        assert dirty_initial_reads == [], "Full reads should stay clean for all platforms"
        assert denied_follow_ups == [], (
            "Full-read unlock should survive relative follow-up paths"
        )

class TestCLIPlatform:
    def test_handle_with_platform_flag(self) -> None:
        """Verify CLI accepts --platform without error."""
        from vibeforcer.cli import build_parser

        parsed = object_dict(
            vars(build_parser().parse_args(["handle", "--platform", "codex"]))
        )
        assert string_value(parsed.get("platform")) == "codex"

    def test_handle_default_platform(self) -> None:
        from vibeforcer.cli import build_parser

        parsed = object_dict(vars(build_parser().parse_args(["handle"])))
        assert string_value(parsed.get("platform")) == "claude"

    def test_replay_with_platform(self) -> None:
        from vibeforcer.cli import build_parser

        parsed = object_dict(
            vars(
                build_parser().parse_args(
                    ["replay", "--payload", "test.json", "--platform", "opencode"]
                )
            )
        )
        assert string_value(parsed.get("platform")) == "opencode"

    def test_invalid_platform_rejected(self) -> None:
        from vibeforcer.cli import build_parser

        with pytest.raises(SystemExit):
            _ = build_parser().parse_args(["handle", "--platform", "vim"])

    def test_safe_main_returns_130_on_keyboard_interrupt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from vibeforcer import cli

        def boom(_argv: object | None = None) -> int:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli, "main", boom)
        assert cli.safe_main() == 130
