from __future__ import annotations

from tests.test_size_guard_hook_behavior import (
    GOD_CLASS_RULE,
    Path,
    QUALITY_LINT_RULE,
    class_with_body_lines,
    enroll_repo,
    opencode_after_payload,
    opencode_before_payload,
    post_bash_payload,
    post_write_payload,
    pre_edit_payload,
    pre_multiedit_payload,
    pre_patch_payload,
    pre_write_payload,
    rule_count,
    assert_hook_prevents,
    evaluate_payload,
)


class TestGodClassLineSpanHookBehavior:
    def test_pretool_write_blocks_god_class_by_line_span(self, tmp_path: Path) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            pre_write_payload(tmp_path, "src/god_by_lines.py", class_with_body_lines())
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, GOD_CLASS_RULE) == 1, result.findings

    def test_opencode_before_write_blocks_god_class_by_line_span(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            opencode_before_payload(
                tmp_path, "src/opencode_god.py", class_with_body_lines()
            ),
            platform="opencode",
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, GOD_CLASS_RULE) == 1, result.findings

    def test_pretool_patch_add_blocks_god_class_by_line_span(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            pre_patch_payload(tmp_path, "src/patched_god.py", class_with_body_lines())
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, GOD_CLASS_RULE) == 1, result.findings

    def test_pretool_edit_blocks_file_already_over_god_class_line_threshold(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            pre_edit_payload(
                tmp_path,
                "src/already_god.py",
                class_with_body_lines(body_lines=401),
                "    attr_0 = None\n",
                "    attr_0 = None  # touched\n",
            )
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, GOD_CLASS_RULE) == 1, result.findings

    def test_pretool_edit_blocks_edit_that_pushes_class_over_line_threshold(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            pre_edit_payload(
                tmp_path,
                "src/pushed_god.py",
                class_with_body_lines(body_lines=400),
                "    attr_399 = None\n",
                "    attr_399 = None\n    attr_400 = None\n",
            )
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, GOD_CLASS_RULE) == 1, result.findings

    def test_pretool_multiedit_blocks_edit_that_pushes_class_over_line_threshold(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            pre_multiedit_payload(
                tmp_path,
                "src/multiedit_pushed_god.py",
                class_with_body_lines(body_lines=400),
                "    attr_399 = None\n",
                "    attr_399 = None\n    attr_400 = None\n",
            )
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, GOD_CLASS_RULE) == 1, result.findings

    def test_posttool_write_blocks_god_class_by_line_span_from_tool_response_path(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            post_write_payload(tmp_path, "src/post_god.py", class_with_body_lines())
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, QUALITY_LINT_RULE) == 1, result.findings

    def test_opencode_after_write_blocks_god_class_by_line_span_from_file_path(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            opencode_after_payload(
                tmp_path, "src/opencode_post_god.py", class_with_body_lines()
            ),
            platform="opencode",
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, QUALITY_LINT_RULE) == 1, result.findings

    def test_posttool_bash_redirection_blocks_god_class_by_line_span(
        self, tmp_path: Path
    ) -> None:
        enroll_repo(tmp_path)
        result = evaluate_payload(
            post_bash_payload(tmp_path, "src/generated_god.py", class_with_body_lines())
        )
        assert_hook_prevents(result, expected_text="god-class")
        assert rule_count(result, QUALITY_LINT_RULE) == 1, result.findings
