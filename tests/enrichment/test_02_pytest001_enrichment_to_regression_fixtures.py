from __future__ import annotations

from tests.test_enrichment import (
    LoadFixture,
    Path,
    RuleFinding,
    Severity,
    _make_conftest,
    _mkdir,
    _pretool_write_payload,
    _write_text,
    enrich_findings,
    evaluate_payload,
    test_support,
)

class TestPYTEST001Enrichment:
    ROULETTE_CODE = (
        "def test_create_user():\n"
        "    user = create_user('alice', 'alice@example.com')\n"
        "    assert user is not None\n"
        "    assert user.name == 'alice'\n"
        "    assert user.email == 'alice@example.com'\n"
        "    assert user.active\n"
    )

    def test_enriched_with_fixtures(self, tmp_project: Path) -> None:
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["user_factory"])

        payload = _pretool_write_payload(
            "tests/test_user.py",
            self.ROULETTE_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-001")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "`user_factory`" in reason, f"Expected fixture in reason: {reason}"

    def test_includes_split_tip(self, tmp_project: Path) -> None:
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)

        payload = _pretool_write_payload(
            "tests/test_user.py",
            self.ROULETTE_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-001")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "splitting" in reason.lower() or "split" in reason.lower(), (
            f"Expected split tip in reason: {reason}"
        )

class TestPYTEST004Enrichment:
    FIXTURE_CODE = (
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def local_db():\n"
        "    return create_session()\n\n"
        "def test_query(local_db):\n"
        "    assert local_db.query(User).count() > 0\n"
    )

    def test_shows_existing_conftest_fixtures(self, tmp_project: Path) -> None:
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["shared_db", "client"])

        payload = _pretool_write_payload(
            "tests/test_db.py",
            self.FIXTURE_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-004")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "`shared_db`" in reason or "`client`" in reason, (
            f"Expected existing fixtures in reason: {reason}"
        )

    def test_suggests_creating_conftest(self, tmp_project: Path) -> None:
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        # No conftest.py at all

        payload = _pretool_write_payload(
            "tests/test_db.py",
            self.FIXTURE_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-004")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "create" in reason.lower() or "no conftest" in reason.lower(), (
            f"Expected create suggestion in reason: {reason}"
        )

class TestPYTEST002Enrichment:
    SLEEP_CODE = (
        "import time\n\n"
        "def test_api_call():\n"
        "    start_server()\n"
        "    time.sleep(5)\n"
        '    response = client.get("/api/v1/health")\n'
        "    assert response.status_code == 200\n"
    )

    def test_enriched_with_fixtures(self, tmp_project: Path) -> None:
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        _make_conftest(tests_dir, ["server"])

        payload = _pretool_write_payload(
            "tests/test_api.py",
            self.SLEEP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-002")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "`server`" in reason, f"Expected fixture in reason: {reason}"

    def test_detects_freezegun_in_requirements(self, tmp_project: Path) -> None:
        tests_dir = tmp_project / "tests"
        _mkdir(tests_dir, exist_ok=True)
        req = tmp_project / "requirements.txt"
        _write_text(req, "freezegun==1.2.3\nrequests\n")

        payload = _pretool_write_payload(
            "tests/test_api.py",
            self.SLEEP_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TEST-002")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "freezegun" in reason.lower(), (
            f"Expected freezegun mention in reason: {reason}"
        )

class TestPYTYPE001Enrichment:
    ANY_DICT_CODE = (
        "from typing import Any\n\n"
        "def process(data: dict[str, Any]) -> dict[str, Any]:\n"
        "    return {k: v for k, v in data.items()}\n"
    )

    ANY_CALLBACK_CODE = (
        "from typing import Any, Callable\n\n"
        "def register_handler(callback: Callable[..., Any]) -> None:\n"
        "    handlers.append(callback)\n"
    )

    def test_suggests_typeddict_for_dicts(self, tmp_project: Path) -> None:
        payload = _pretool_write_payload(
            "src/models.py",
            self.ANY_DICT_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TYPE-001")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "TypedDict" in reason, f"Expected TypedDict suggestion: {reason}"

    def test_suggests_callable_for_callbacks(self, tmp_project: Path) -> None:
        payload = _pretool_write_payload(
            "src/handlers.py",
            self.ANY_CALLBACK_CODE,
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        test_support.assert_denied_by(result, "PY-TYPE-001")

        reason = test_support.required_string(
            test_support.hook_output(result), "permissionDecisionReason"
        )
        assert "Callable" in reason, f"Expected Callable suggestion: {reason}"

class TestEnrichmentSafety:
    def test_enrichment_error_swallowed(self, tmp_project: Path) -> None:
        """Even if enrichment throws, the deny still comes through."""
        payload = _pretool_write_payload(
            "tests/test_items.py",
            "def test_all():\n    for x in [1,2]:\n        assert x > 0\n",
            str(tmp_project),
        )
        result = evaluate_payload(payload)
        # Should still deny regardless of enrichment
        test_support.assert_denied_by(result, "PY-TEST-003")
        assert "PY-TEST-003" in test_support.finding_ids(result), (
            "enrichment failures must not remove the original loop-assert finding"
        )

    def test_original_message_preserved(self) -> None:
        """Enrichment should append, not replace the original message."""
        finding = RuleFinding(
            rule_id="PY-TEST-003",
            title="test",
            severity=Severity.HIGH,
            decision="deny",
            message="Original denial message",
            metadata={"hits": []},
        )
        # With no hits, enrichment should be a no-op
        from vibeforcer.context import build_context

        ctx = build_context(
            {
                "session_id": "t",
                "cwd": "/tmp",
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {},
            }
        )
        enrich_findings([finding], ctx)
        assert finding.message is not None
        assert finding.message.startswith("Original denial message")

class TestRegressionFixtures:
    """Verify the original fixture tests still produce correct denials.

    These run against the bundle fixtures (not tmp_project) where there's
    no conftest.py to discover — enrichment should add nothing harmful.
    """

    def test_loop_assert_fixture(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_test_loop_assert.json"))
        test_support.assert_denied_by(result, "PY-TEST-003")
        assert "PY-TEST-003" in test_support.finding_ids(result), (
            "bundle loop fixture should keep reporting PY-TEST-003"
        )

    def test_assertion_roulette_fixture(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_assertion_roulette.json"))
        test_support.assert_denied_by(result, "PY-TEST-001")
        assert "PY-TEST-001" in test_support.finding_ids(result), (
            "bundle assertion-roulette fixture should keep reporting PY-TEST-001"
        )

    def test_test_sleep_fixture(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_test_sleep.json"))
        test_support.assert_denied_by(result, "PY-TEST-002")
        assert "PY-TEST-002" in test_support.finding_ids(result), (
            "bundle sleep fixture should keep reporting PY-TEST-002"
        )

    def test_fixture_outside_conftest_fixture(self, load_fixture: LoadFixture) -> None:
        result = evaluate_payload(load_fixture("pretool_fixture_outside_conftest.json"))
        test_support.assert_denied_by(result, "PY-TEST-004")
        assert "PY-TEST-004" in test_support.finding_ids(result), (
            "bundle local-fixture fixture should keep reporting PY-TEST-004"
        )
