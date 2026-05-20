from __future__ import annotations

from tests.test_hook_state_spec import (
    Path,
    Severity,
    _assert_loop_steering_metadata,
    _assert_repeat_counts,
    _enable_loop_rules,
    _enable_thin_wrapper_rule,
    _evaluate_thin_wrapper_hits,
    _finding,
    _posttool_payload,
    _repeat_tracking_repair_sequence,
    _require_finding,
    _require_subprocess_finding,
    _run_thin_wrapper_subprocess_hit,
    evaluate_payload,
    finding_ids,
    pytest,
)

class TestRepeatedDebtEscalationSpec:
    def test_second_thin_wrapper_hit_tracks_repeat_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_thin_wrapper_rule(tmp_path, monkeypatch)
        first, second = _evaluate_thin_wrapper_hits(tmp_path, 2)

        first_finding = _require_finding("PY-CODE-013", first.findings)
        second_finding = _require_finding("PY-CODE-013", second.findings)
        assert first_finding.rule_id == second_finding.rule_id == "PY-CODE-013", (
            "thin-wrapper repeat tracking should inspect the same rule across hits"
        )
        _assert_repeat_counts(
            first_finding,
            second_finding,
            expected_first=1,
            expected_second=2,
        )

    def test_third_thin_wrapper_hit_escalates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_thin_wrapper_rule(tmp_path, monkeypatch)
        third = _evaluate_thin_wrapper_hits(tmp_path, 3)[-1]

        finding = _finding("PY-CODE-013", third.findings)
        assert finding is not None
        assert finding.metadata.get("repeat_count") == 3
        assert finding.severity >= Severity.HIGH or finding.decision in {"deny", "block"}

    def test_repeat_tracking_is_scoped_per_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_thin_wrapper_rule(tmp_path, monkeypatch)
        code = "def get_all_users():\n    return UserRepository.find_all()\n"
        _ = evaluate_payload(
            _posttool_payload(
                cwd=tmp_path,
                rel_path="src/one.py",
                code=code,
                session_id="repeat-session",
            )
        )
        second_path = evaluate_payload(
            _posttool_payload(
                cwd=tmp_path,
                rel_path="src/two.py",
                code=code,
                session_id="repeat-session",
            )
        )

        finding = _finding("PY-CODE-013", second_path.findings)
        assert finding is not None
        assert finding.metadata.get("repeat_count") == 1

    def test_repeat_tracking_resets_after_clean_repair_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_thin_wrapper_rule(tmp_path, monkeypatch)
        repaired, repeated_after_repair = _repeat_tracking_repair_sequence(tmp_path)

        repaired_finding = _finding("PY-CODE-013", repaired.findings)
        repeated_finding = _finding("PY-CODE-013", repeated_after_repair.findings)
        assert repaired_finding is None, (
            "Clean repair write should not keep the thin-wrapper finding active"
        )
        assert repeated_finding is not None, (
            "Reintroduced thin wrapper should produce a new PY-CODE-013 finding"
        )
        assert repeated_finding.metadata.get("repeat_count") == 1, (
            "Repeat counter should reset after the path is repaired cleanly"
        )

    def test_new_session_resets_repeat_counter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_thin_wrapper_rule(tmp_path, monkeypatch)
        code = "def get_all_users():\n    return UserRepository.find_all()\n"
        _ = evaluate_payload(
            _posttool_payload(
                cwd=tmp_path,
                rel_path="src/thin.py",
                code=code,
                session_id="session-a",
            )
        )
        result = evaluate_payload(
            _posttool_payload(
                cwd=tmp_path,
                rel_path="src/thin.py",
                code=code,
                session_id="session-b",
            )
        )

        finding = _finding("PY-CODE-013", result.findings)
        assert finding is not None
        assert finding.metadata.get("repeat_count") == 1

    def test_repeat_count_must_survive_subprocess_boundary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_thin_wrapper_rule(tmp_path, monkeypatch)
        first = _run_thin_wrapper_subprocess_hit(tmp_path)
        second = _run_thin_wrapper_subprocess_hit(tmp_path)

        first_finding = _require_subprocess_finding("PY-CODE-013", first)
        second_finding = _require_subprocess_finding("PY-CODE-013", second)
        assert first_finding["metadata"].get("repeat_count") == 1
        assert second_finding["metadata"].get("repeat_count") == 2

class TestLoopAwareDenialSteering:
    def test_second_hit_adds_failure_class_and_repeat_metadata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_loop_rules(tmp_path, monkeypatch)
        first, second = _evaluate_thin_wrapper_hits(tmp_path, 2, "loop-session")
        first_finding = _require_finding("PY-CODE-013", first.findings)
        second_finding = _require_finding("PY-CODE-013", second.findings)
        assert first_finding.rule_id == second_finding.rule_id == "PY-CODE-013", (
            "loop steering metadata should be attached to repeated thin-wrapper hits"
        )
        _assert_loop_steering_metadata(first_finding, second_finding)

    def test_third_write_is_blocked_after_repeat_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_loop_rules(tmp_path, monkeypatch)
        payload = {
            "session_id": "budget-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/api.py",
                "content": "def f(a,b,c,d,e,f,g,h):\n    return 1\n",
            },
        }
        _ = evaluate_payload(payload)
        _ = evaluate_payload(payload)
        third = evaluate_payload(payload)
        assert "RETRY-BUDGET-001" in finding_ids(third)

    def test_third_write_is_not_blocked_when_code_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_loop_rules(tmp_path, monkeypatch)
        repeated_payload = {
            "session_id": "budget-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/api.py",
                "content": "def f(a,b,c,d,e,f,g,h):\n    return 1\n",
            },
        }
        changed_payload = {
            "session_id": "budget-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/api.py",
                "content": "def f(params):\n    return params\n",
            },
        }

        _ = evaluate_payload(repeated_payload)
        _ = evaluate_payload(repeated_payload)
        third = evaluate_payload(changed_payload)

        assert "RETRY-BUDGET-001" not in finding_ids(third)

    def test_third_write_is_not_blocked_when_triggered_rule_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_loop_rules(tmp_path, monkeypatch)
        repeated_payload = {
            "session_id": "budget-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/api.py",
                "content": "def f(a,b,c,d,e,f,g,h):\n    return 1\n",
            },
        }
        changed_rule_payload = {
            "session_id": "budget-session",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/api.py",
                "content": "def get_all_users():\n    return UserRepository.find_all()\n",
            },
        }

        _ = evaluate_payload(repeated_payload)
        _ = evaluate_payload(repeated_payload)
        third = evaluate_payload(changed_rule_payload)

        assert "RETRY-BUDGET-001" not in finding_ids(third)
        assert "PY-CODE-013" in finding_ids(third)

    def test_session_start_includes_recent_repeated_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_loop_rules(tmp_path, monkeypatch)
        code = "def get_all_users():\n    return UserRepository.find_all()\n"
        _ = evaluate_payload(
            _posttool_payload(
                cwd=tmp_path,
                rel_path="src/thin.py",
                code=code,
                session_id="memory-session",
            )
        )
        _ = evaluate_payload(
            _posttool_payload(
                cwd=tmp_path,
                rel_path="src/thin.py",
                code=code,
                session_id="memory-session",
            )
        )
        session_start = evaluate_payload(
            {
                "session_id": "memory-session",
                "cwd": str(tmp_path),
                "hook_event_name": "SessionStart",
                "tool_name": "",
                "tool_input": {},
            }
        )
        assert "SESSION-RECENT-FAILURES" in finding_ids(session_start)
