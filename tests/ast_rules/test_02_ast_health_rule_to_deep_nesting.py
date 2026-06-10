from __future__ import annotations

from tests.test_ast_rules import (
    BUNDLE_ROOT,
    Path,
    TemporaryDirectory,
    assert_denied_by,
    assert_not_denied,
    permission_reason,
    evaluate_payload,
    string_value,
    unittest,
)


class TestAstHealthRule(unittest.TestCase):
    def test_write_invalid_syntax_still_triggers_parse_failure(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/main.py",
                "content": "def broken(:\n    pass\n",
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-AST-001")
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" in rule_ids, "invalid write must emit parse failure"

    def test_parse_failure_reason_gives_compile_recovery(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/main.py",
                "content": "def broken(:\n    pass\n",
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-AST-001")
        reason = permission_reason(result)

        assert "python3 -m py_compile src/main.py" in reason
        assert "test -e src/main.py" not in reason

    def test_parse_failure_reason_shell_quotes_path(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/broken file.py",
                "content": "def broken(:\n    pass\n",
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-AST-001")
        reason = permission_reason(result)

        assert "python3 -m py_compile 'src/broken file.py'" in reason

    def test_read_error_reason_checks_path_before_compile(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir) / "repo"
            repo.mkdir(parents=True)
            _ = (repo / "slopgate.toml").write_text(
                "[slopgate]\nenabled = true\n",
                encoding="utf-8",
            )
            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "missing.py"},
                "cwd": str(repo),
                "session_id": "t",
            }
            result = evaluate_payload(payload)

        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" in rule_ids
        assert result.output is not None
        reason = string_value(result.output.get("reason")) or ""
        assert "test -e missing.py" in reason
        assert "re-read the moved/renamed file" in reason

    def test_read_error_reason_shell_quotes_path(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir) / "repo"
            repo.mkdir(parents=True)
            _ = (repo / "slopgate.toml").write_text(
                "[slopgate]\nenabled = true\n",
                encoding="utf-8",
            )
            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "missing file.py"},
                "cwd": str(repo),
                "session_id": "t",
            }
            result = evaluate_payload(payload)

        assert result.output is not None
        reason = string_value(result.output.get("reason")) or ""
        assert "test -e 'missing file.py'" in reason

    def test_edit_fragment_does_not_trigger_parse_failure(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/main.py",
                "new_string": "        self._controller = controller\n",
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" not in rule_ids

    def test_patch_fragment_does_not_trigger_parse_failure(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Patch",
            "tool_input": {
                "patch": (
                    "*** Begin Patch\n"
                    "*** Update File: src/main.py\n"
                    "@@\n"
                    "+        self._controller = controller\n"
                    "*** End Patch\n"
                )
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" not in rule_ids

    def test_multiedit_fragment_does_not_trigger_parse_failure(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [
                    {
                        "file_path": "src/main.py",
                        "old_string": "self.value = 0\n",
                        "new_string": "        self.value = value\n",
                    }
                ]
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" not in rule_ids

    def test_opencode_edit_fragment_does_not_trigger_parse_failure(self) -> None:
        payload = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "edit",
            "tool_input": {
                "file_path": "src/main.py",
                "new_string": "        self._controller = controller\n",
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload, platform="opencode")
        assert result.event_name == "PreToolUse"
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" not in rule_ids

    def test_opencode_write_indented_fragment_does_not_trigger_parse_failure(
        self,
    ) -> None:
        payload = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "write",
            "tool_input": {
                "filePath": "src/main.py",
                "content": "        self._controller = controller\n",
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload, platform="opencode")
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" not in rule_ids

    def test_opencode_morph_fragment_does_not_trigger_parse_failure(self) -> None:
        payload = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "morph",
            "tool_input": {
                "filePath": "src/main.py",
                "content": (
                    "def _repaint_table(\n"
                    "    table: DataTable[str], rows: Sequence[Row],\n"
                    ") -> None:\n"
                    "// ... existing code ...]\n"
                ),
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload, platform="opencode")
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" not in rule_ids

    def test_opencode_write_invalid_full_module_still_triggers_parse_failure(
        self,
    ) -> None:
        payload = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "write",
            "tool_input": {
                "filePath": "src/main.py",
                "content": "def broken(:\n    pass\n",
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload, platform="opencode")
        assert result.output is not None
        assert result.output.get("action") == "block"
        reason = string_value(result.output.get("reason")) or ""
        assert "PY-AST-001" in reason

    def test_posttool_indented_file_still_triggers_parse_failure(
        self,
    ) -> None:
        with TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir) / "repo"
            repo.mkdir(parents=True)
            _ = (repo / "slopgate.toml").write_text(
                "[slopgate]\nenabled = true\n",
                encoding="utf-8",
            )
            _ = (repo / "broken.py").write_text("    x = 1\n", encoding="utf-8")
            payload = {
                "hook_event_name": "tool.execute.after",
                "tool_name": "write",
                "tool_input": {"filePath": "broken.py"},
                "cwd": str(repo),
                "session_id": "t",
            }
            result = evaluate_payload(payload, platform="opencode")
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-AST-001" in rule_ids


class TestDeepNesting(unittest.TestCase):
    def test_deep_blocked(self) -> None:
        code = (
            "def f():\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    if e:\n"
            "                        return 1\n"
            "    return 0"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-CODE-011")
        assert any(finding.rule_id == "PY-CODE-011" for finding in result.findings)

    def test_depth_4_ok(self) -> None:
        code = (
            "def f():\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    return 1\n"
            "    return 0"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-011" for finding in result.findings)
