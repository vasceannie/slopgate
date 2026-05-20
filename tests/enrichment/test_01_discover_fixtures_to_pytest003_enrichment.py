from __future__ import annotations

from tests.test_enrichment import (
    Path,
    _make_conftest,
    _make_sibling_test,
    _mkdir,
    _pretool_write_payload,
    _write_text,
    discover_fixtures,
    evaluate_payload,
    find_parametrize_examples,
    test_support,
    time,
)

class TestDiscoverFixtures:
    def test_finds_fixtures_in_same_dir(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        _make_conftest(tests_dir, ["db_session", "client", "auth_token"])
        test_file = tests_dir / "test_api.py"
        _write_text(test_file, "# test file")

        fixtures = discover_fixtures(test_file, tmp_path)
        names = {f["name"] for f in fixtures}
        assert names == {"db_session", "client", "auth_token"}

    def test_finds_fixtures_in_parent_dir(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        sub_dir = tests_dir / "api"
        _mkdir(sub_dir, parents=True)
        _make_conftest(tests_dir, ["root_fixture"])
        _make_conftest(sub_dir, ["api_fixture"])
        test_file = sub_dir / "test_endpoints.py"
        _write_text(test_file, "# test")

        fixtures = discover_fixtures(test_file, tmp_path)
        names = {f["name"] for f in fixtures}
        assert "api_fixture" in names
        assert "root_fixture" in names

    def test_identifies_parametrized_fixtures(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        _make_conftest(
            tests_dir, ["normal", "data_driven"], with_params=["data_driven"]
        )
        test_file = tests_dir / "test_x.py"
        _write_text(test_file, "# test")

        fixtures = discover_fixtures(test_file, tmp_path)
        by_name = {f["name"]: f for f in fixtures}
        assert by_name["normal"]["has_params"] is False
        assert by_name["data_driven"]["has_params"] is True

    def test_no_conftest_returns_empty(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        test_file = tests_dir / "test_x.py"
        _write_text(test_file, "# test")

        fixtures = discover_fixtures(test_file, tmp_path)
        assert fixtures == []

    def test_caps_at_10(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        _make_conftest(tests_dir, [f"fix_{i}" for i in range(15)])
        test_file = tests_dir / "test_x.py"
        _write_text(test_file, "# test")

        fixtures = discover_fixtures(test_file, tmp_path)
        assert len(fixtures) <= 10

    def test_handles_syntax_error_in_conftest(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        conftest = tests_dir / "conftest.py"
        _write_text(conftest, "def broken(:\n    pass\n")
        test_file = tests_dir / "test_x.py"
        _write_text(test_file, "# test")

        # Should not raise, just return empty
        fixtures = discover_fixtures(test_file, tmp_path)
        assert fixtures == []

class TestFindParametrizeExamples:
    def test_finds_sibling_parametrize(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        _make_sibling_test(tests_dir, "test_math.py", has_parametrize=True)
        test_file = tests_dir / "test_target.py"
        _write_text(test_file, "# target")

        examples = find_parametrize_examples(test_file, tmp_path)
        assert len(examples) >= 1
        assert "parametrize" in examples[0]["snippet"]
        assert examples[0]["file"] == "test_math.py"

    def test_skips_self(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        test_file = tests_dir / "test_target.py"
        _write_text(
            test_file,
            '@pytest.mark.parametrize("x", [1])\ndef test_self(x):\n    pass\n',
        )

        examples = find_parametrize_examples(test_file, tmp_path)
        assert len(examples) == 0

    def test_caps_at_max(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        for i in range(5):
            _make_sibling_test(tests_dir, f"test_sibling_{i}.py", has_parametrize=True)
        test_file = tests_dir / "test_target.py"
        _write_text(test_file, "# target")

        examples = find_parametrize_examples(test_file, tmp_path, max_examples=2)
        assert len(examples) <= 2

    def test_no_siblings_returns_empty(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        _mkdir(tests_dir)
        test_file = tests_dir / "test_target.py"
        _write_text(test_file, "# alone")

        examples = find_parametrize_examples(test_file, tmp_path)
        assert examples == []

class TestPYTEST003Enrichment:
    """Test that PY-TEST-003 denials include enriched context when
    the filesystem has conftest.py and sibling tests."""

    LOOP_CODE = (
        "def test_all_items_valid():\n"
        "    items = get_items()\n"
        "    for item in items:\n"
        "        assert item.is_valid()\n"
    )

    def test_enriched_with_fixtures(self, tmp_project: Path) -> None:
        """When conftest.py has fixtures, denial message includes them."""
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["db_session", "client"])

        payload = _pretool_write_payload(
            "tests/test_items.py",
            self.LOOP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-003")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "`db_session`" in reason or "`client`" in reason, (
            f"Expected fixture names in reason, got: {reason}"
        )

    def test_enriched_with_parametrize_examples(self, tmp_project: Path) -> None:
        """When siblings have parametrize, denial message includes examples."""
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["fixture_a"])
        _make_sibling_test(tests_dir, "test_math.py", has_parametrize=True)

        payload = _pretool_write_payload(
            "tests/test_items.py",
            self.LOOP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-003")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "test_math.py" in reason, f"Expected sibling ref in reason: {reason}"

    def test_enriched_additional_context(self, tmp_project: Path) -> None:
        """Claude Code additional_context includes extended fixture list."""
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["db", "client", "auth"])

        payload = _pretool_write_payload(
            "tests/test_items.py",
            self.LOOP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-003")

        context = test_support.output_string(
            test_support.hook_output(result), "additionalContext"
        )
        assert "AVAILABLE FIXTURES" in context or "COMPLIANT ALTERNATIVES" in context, (
            f"Expected enrichment in additionalContext: {context}"
        )

    def test_still_denies_without_fixtures(self, tmp_project: Path) -> None:
        """PY-TEST-003 still fires even with no conftest.py (just no enrichment)."""
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        # No conftest.py

        payload = _pretool_write_payload(
            "tests/test_items.py",
            self.LOOP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-003")
        assert "PY-TEST-003" in test_support.finding_ids(result), (
            "loop-assert writes should still report the test-loop rule without fixture enrichment"
        )

    def test_loop_assert_regex_does_not_backtrack_on_large_patch(
        self, tmp_project: Path
    ) -> None:
        """Large generated loop patches without asserts should not hang hooks."""
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        filler = "".join(
            f"        value_{index} = expensive_setup(row)\n" for index in range(180)
        )
        content = (
            "def test_contract_rows():\n"
            "    for row in rows:\n"
            f"{filler}"
        )
        payload = _pretool_write_payload(
            "tests/test_contract_rows.py",
            content,
            str(tmp_project),
        )

        started = time.monotonic()
        result = evaluate_payload(payload)
        elapsed = time.monotonic() - started

        assert elapsed < 1.0
        assert "PY-TEST-003" not in test_support.finding_ids(result)

    def test_cross_platform_codex(self, tmp_project: Path) -> None:
        """Codex adapter: enrichment lands in permissionDecisionReason."""
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["db_session"])

        payload = _pretool_write_payload(
            "tests/test_items.py",
            self.LOOP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload, platform="codex")
        assert result.output is not None
        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "PY-TEST-003" in reason
        assert "`db_session`" in reason, (
            f"Codex reason should include fixture names: {reason}"
        )

    def test_cross_platform_opencode(self, tmp_project: Path) -> None:
        """OpenCode adapter: enrichment lands in reason field."""
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["db_session"])

        payload = _pretool_write_payload(
            "tests/test_items.py",
            self.LOOP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload, platform="opencode")
        assert result.output is not None
        reason = test_support.required_string(
            test_support.require_output(result), "reason"
        )
        assert "PY-TEST-003" in reason
        assert "`db_session`" in reason, (
            f"OpenCode reason should include fixture names: {reason}"
        )
