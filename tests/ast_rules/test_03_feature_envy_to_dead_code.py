from __future__ import annotations

from tests.test_ast_rules import (
    BUNDLE_ROOT,
    _assert_denied_by,
    _assert_not_denied,
    evaluate_payload,
    unittest,
)

class TestFeatureEnvy(unittest.TestCase):
    def test_param_exempt(self) -> None:
        """Accessing attributes of a function parameter is not feature envy."""
        code = (
            "def f(order):\n"
            "    a = order.total\n"
            "    b = order.items\n"
            "    c = order.status\n"
            "    d = order.customer\n"
            "    e = order.address\n"
            "    f = order.created\n"
            "    return a"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-012" for finding in result.findings)

    def test_envy_nonparam_context(self) -> None:
        """Accessing a non-param object heavily should produce context, not deny."""
        code = (
            "def f():\n"
            "    import db\n"
            "    a = db.total\n"
            "    b = db.items\n"
            "    c = db.status\n"
            "    d = db.customer\n"
            "    e = db.address\n"
            "    f = db.created\n"
            "    return a"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        # Should NOT be denied (decision is now context, not deny)
        _assert_not_denied(result)
        assert any(finding.rule_id == "PY-CODE-012" for finding in result.findings)

    def test_self_exempt(self) -> None:
        code = (
            "def f(self):\n    a = self.x\n    b = self.y\n    c = self.z\n    return a"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-012" for finding in result.findings)

class TestThinWrapper(unittest.TestCase):
    def test_thin_blocked(self) -> None:
        code = "def get_value(obj):\n    return get_value(obj)"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_denied_by(result, "PY-CODE-013")
        assert any(finding.rule_id == "PY-CODE-013" for finding in result.findings)

    def test_dunder_exempt(self) -> None:
        code = "def __str__(self):\n    return str(self.value)"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-013" for finding in result.findings)

    def test_decorated_exempt(self) -> None:
        code = "@cached\ndef get_value(obj):\n    return get_value(obj)"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-013" for finding in result.findings)

    def test_cast_wrapper_exempt(self) -> None:
        code = (
            "from typing import cast\n\n"
            "def factory(value: object) -> str:\n"
            "    return cast(str, value)\n"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-013" not in rule_ids, "typing.cast wrapper should stay exempt"

    def test_test_helper_self_delegate_exempt(self) -> None:
        code = (
            "class Recorder:\n"
            "    def _record(self, action: str) -> None:\n"
            "        pass\n\n"
            "    def pause(self) -> None:\n"
            "        return self._record('pause')\n"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "tests/tui/conftest.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-013" not in rule_ids, "test helper self-delegate should stay exempt"

    def test_test_helper_list_wrapper_exempt(self) -> None:
        code = (
            "class FakeRuns:\n"
            "    def __init__(self, runs: list[str]) -> None:\n"
            "        self._runs = runs\n\n"
            "    def list_runs(self) -> list[str]:\n"
            "        return list(self._runs)\n"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "tests/tui/conftest.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-013" not in rule_ids, "test helper list wrapper should stay exempt"

class TestGodClass(unittest.TestCase):
    def test_god_blocked(self) -> None:
        methods = chr(10).join([f"    def m{i}(self): pass" for i in range(1, 12)])
        code = f"class C:\n{methods}"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_denied_by(result, "PY-CODE-014")
        assert any(finding.rule_id == "PY-CODE-014" for finding in result.findings)

    def test_10_methods_ok(self) -> None:
        methods = chr(10).join([f"    def m{i}(self): pass" for i in range(1, 11)])
        code = f"class C:\n{methods}"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-014" for finding in result.findings)

class TestCyclomaticComplexity(unittest.TestCase):
    def test_complex_blocked(self) -> None:
        conds = chr(10).join([f"    if a{i}: return {i}" for i in range(1, 13)])
        code = f"def f():\n{conds}\n    return 0"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_denied_by(result, "PY-CODE-015")
        assert any(finding.rule_id == "PY-CODE-015" for finding in result.findings)

    def test_complexity_10_ok(self) -> None:
        conds = chr(10).join([f"    if a{i}: return {i}" for i in range(1, 10)])
        code = f"def f():\n{conds}\n    return 0"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-015" for finding in result.findings)

class TestDeadCode(unittest.TestCase):
    def test_dead_blocked(self) -> None:
        code = 'def f(x):\n    if x:\n        return 1\n        print("dead")\n    return 0'
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_denied_by(result, "PY-CODE-016")
        assert any(finding.rule_id == "PY-CODE-016" for finding in result.findings)

    def test_return_at_end_ok(self) -> None:
        code = "def f(x):\n    if x:\n        return 1\n    return 0"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-016" for finding in result.findings)
