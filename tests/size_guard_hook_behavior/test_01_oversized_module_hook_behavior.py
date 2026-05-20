from __future__ import annotations

from tests.test_size_guard_hook_behavior import (
    OVERSIZED_MODULE_RULE,
    Path,
    QUALITY_LINT_RULE,
    _assignment_module,
    _enroll_repo,
    _finding_ids,
    _findings_for_rule,
    _opencode_after_payload,
    _opencode_before_edit_payload,
    _opencode_before_payload,
    _post_write_payload,
    _pre_edit_payload,
    _pre_patch_payload,
    _pre_write_payload,
    _result_text,
    _rule_count,
    assert_hook_prevents,
    evaluate_payload,
)

class TestOversizedModuleHookBehavior:
    def test_pretool_write_blocks_soft_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/soft_oversized.py", _assignment_module(351))
        )
        assert_hook_prevents(result, expected_text="oversized")
        findings = _findings_for_rule(result, OVERSIZED_MODULE_RULE)
        assert len(findings) == 1, result.findings
        assert "code-hygiene-refactor" in (findings[0].additional_context or ""), (
            findings[0].additional_context
        )
        assert "hygiene-orchestrator" in (findings[0].additional_context or ""), (
            findings[0].additional_context
        )

    def test_pretool_write_blocks_hard_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/hard_oversized.py", _assignment_module(601))
        )
        assert_hook_prevents(result, expected_text="oversized")
        assert _rule_count(result, OVERSIZED_MODULE_RULE) == 1, result.findings

    def test_pretool_write_gives_conftest_split_guidance(self, tmp_path: Path) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "tests/tui/conftest.py", _assignment_module(601))
        )

        assert_hook_prevents(result, expected_text="conftest")
        findings = _findings_for_rule(result, OVERSIZED_MODULE_RULE)
        assert len(findings) == 1, result.findings
        assert findings[0].metadata["split_scenario"] == "conftest", findings[0].metadata
        assert "fixture registry" in (findings[0].additional_context or ""), (
            findings[0].additional_context
        )
        assert "tests/<area>/support/" in (findings[0].additional_context or ""), (
            findings[0].additional_context
        )

    def test_pretool_write_gives_module_to_package_guidance(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/job_hunter/dashboard.py", _assignment_module(601))
        )

        assert_hook_prevents(result, expected_text="module-to-package")
        findings = _findings_for_rule(result, OVERSIZED_MODULE_RULE)
        assert len(findings) == 1, result.findings
        assert findings[0].metadata["split_scenario"] == "module-to-package", (
            findings[0].metadata
        )
        assert "re-exporting the old public API" in (
            findings[0].additional_context or ""
        ), findings[0].additional_context
        assert "resources, or builders" in (findings[0].additional_context or ""), (
            findings[0].additional_context
        )

    def test_pretool_write_gives_entrypoint_router_guidance(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/job_hunter/routes.py", _assignment_module(601))
        )

        assert_hook_prevents(result, expected_text="entrypoint-or-router")
        findings = _findings_for_rule(result, OVERSIZED_MODULE_RULE)
        assert len(findings) == 1, result.findings
        assert findings[0].metadata["split_scenario"] == "entrypoint-or-router", (
            findings[0].metadata
        )
        assert "commands/routes stay thin" in (findings[0].additional_context or ""), (
            findings[0].additional_context
        )

    def test_pretool_write_gives_package_init_guidance(self, tmp_path: Path) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_write_payload(tmp_path, "src/job_hunter/__init__.py", _assignment_module(601))
        )

        assert_hook_prevents(result, expected_text="package-init")
        findings = _findings_for_rule(result, OVERSIZED_MODULE_RULE)
        assert len(findings) == 1, result.findings
        assert findings[0].metadata["split_scenario"] == "package-init", findings[0].metadata
        assert "facade only" in (findings[0].additional_context or ""), (
            findings[0].additional_context
        )

    def test_opencode_before_write_blocks_soft_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_before_payload(
                tmp_path, "src/opencode_soft.py", _assignment_module(351)
            ),
            platform="opencode",
        )
        assert_hook_prevents(result, expected_text="oversized")
        assert _rule_count(result, OVERSIZED_MODULE_RULE) == 1, result.findings

    def test_pretool_patch_add_blocks_soft_oversized_python_module(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_patch_payload(tmp_path, "src/patched_soft.py", _assignment_module(351))
        )
        assert_hook_prevents(result, expected_text="oversized")
        assert _rule_count(result, OVERSIZED_MODULE_RULE) == 1, result.findings

    def test_pretool_edit_blocks_file_already_over_soft_module_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_edit_payload(
                tmp_path,
                "src/already_oversized.py",
                _assignment_module(351),
                "VALUE_0 = None\n",
                "VALUE_0 = None  # touched\n",
            )
        )
        assert_hook_prevents(result, expected_text="oversized")
        assert _rule_count(result, OVERSIZED_MODULE_RULE) == 1, result.findings

    def test_pretool_edit_blocks_edit_that_pushes_module_over_soft_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _pre_edit_payload(
                tmp_path,
                "src/pushed_oversized.py",
                _assignment_module(350),
                "VALUE_349 = None\n",
                "VALUE_349 = None\nVALUE_350 = None\n",
            )
        )
        assert_hook_prevents(result, expected_text="oversized")
        assert _rule_count(result, OVERSIZED_MODULE_RULE) == 1, result.findings

    def test_opencode_before_edit_blocks_edit_that_pushes_module_over_soft_threshold(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_before_edit_payload(
                tmp_path,
                "src/opencode_pushed_oversized.py",
                _assignment_module(350),
                "VALUE_349 = None\n",
                "VALUE_349 = None\nVALUE_350 = None\n",
            ),
            platform="opencode",
        )
        assert_hook_prevents(result, expected_text="oversized")
        assert _rule_count(result, OVERSIZED_MODULE_RULE) == 1, result.findings

    def test_posttool_write_blocks_soft_oversized_python_module_from_tool_response_path(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _post_write_payload(
                tmp_path, "src/post_soft.py", _assignment_module(351)
            )
        )
        assert_hook_prevents(result, expected_text="oversized-module-soft")
        rule_ids = _finding_ids(result)
        details = _result_text(result)
        assert rule_ids.count(QUALITY_LINT_RULE) == 1, rule_ids
        assert OVERSIZED_MODULE_RULE not in rule_ids, rule_ids
        assert "module-to-package split plan" in details, details
        assert "code-hygiene-refactor" in details, details
        assert "hygiene-orchestrator" in details, details

    def test_posttool_write_uses_single_conftest_oversized_recommendation(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _post_write_payload(
                tmp_path, "tests/tui/conftest.py", _assignment_module(351)
            )
        )

        assert_hook_prevents(result, expected_text="oversized-module-soft")
        rule_ids = _finding_ids(result)
        details = _result_text(result)
        assert rule_ids.count(QUALITY_LINT_RULE) == 1, rule_ids
        assert OVERSIZED_MODULE_RULE not in rule_ids, rule_ids
        assert "conftest split" in details, details
        assert "fixture registry" in details, details

    def test_opencode_after_write_blocks_soft_oversized_python_module_from_file_path(
        self, tmp_path: Path
    ) -> None:
        _enroll_repo(tmp_path)
        result = evaluate_payload(
            _opencode_after_payload(
                tmp_path, "src/opencode_post_soft.py", _assignment_module(351)
            ),
            platform="opencode",
        )
        assert_hook_prevents(result, expected_text="oversized-module-soft")
        rule_ids = _finding_ids(result)
        assert rule_ids.count(QUALITY_LINT_RULE) == 1, rule_ids
        assert OVERSIZED_MODULE_RULE not in rule_ids, rule_ids
