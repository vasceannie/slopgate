from __future__ import annotations

from tests.test_ast_rules import (
    BUNDLE_ROOT,
    Path,
    TemporaryDirectory,
    assert_denied_by,
    assert_not_denied,
    evaluate_payload,
    unittest,
)

FEATURE_ENVY_PATH = "src/main.py"


def _post_write_payload(root: Path, code: str) -> dict[str, object]:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    target = root / FEATURE_ENVY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": FEATURE_ENVY_PATH, "content": code},
        "tool_response": {"filePath": FEATURE_ENVY_PATH, "success": True},
        "cwd": str(root),
    }


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
        with TemporaryDirectory() as tmp_dir:
            result = evaluate_payload(_post_write_payload(Path(tmp_dir), code))
        assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-012" for finding in result.findings)

    def test_envy_nonparam_context(self) -> None:
        """Accessing a non-param object heavily should produce context, not deny."""
        code = (
            "service = object()\n\n"
            "def f():\n"
            "    return (\n"
            "        service.total\n"
            "        + service.items\n"
            "        + service.status\n"
            "        + service.customer\n"
            "        + service.address\n"
            "        + service.created\n"
            "    )"
        )
        with TemporaryDirectory() as tmp_dir:
            result = evaluate_payload(_post_write_payload(Path(tmp_dir), code))
        # Should NOT be denied (decision is now context, not deny)
        assert_not_denied(result)
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
        assert_not_denied(result)
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
        assert_denied_by(result, "PY-CODE-013")
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
        assert_not_denied(result)
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
        assert_not_denied(result)
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
        assert_not_denied(result)
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
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-013" not in rule_ids, (
            "test helper self-delegate should stay exempt"
        )

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
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-013" not in rule_ids, (
            "test helper list wrapper should stay exempt"
        )

    def test_test_helper_tuple_wrapper_exempt(self) -> None:
        code = (
            "def order_case(order_id: str, expected: int) -> tuple[str, int]:\n"
            "    return tuple((order_id, expected))\n"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "tests/orders/test_cases.py",
                "new_string": code,
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-013" not in rule_ids, (
            "test helper tuple fixture-shape wrapper should be allowed"
        )

    def test_test_helper_dict_wrapper_exempt(self) -> None:
        code = (
            "def order_payload(order_id: str) -> dict[str, str]:\n"
            "    return dict(order_id=order_id)\n"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "tests/orders/conftest.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_not_denied(result)
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-013" not in rule_ids, (
            "test helper dict fixture-shape wrapper should be allowed"
        )

    def test_test_helper_str_wrapper_is_still_denied(self) -> None:
        code = "def order_id_text(order_id: object) -> str:\n    return str(order_id)\n"
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "tests/orders/test_cases.py",
                "new_string": code,
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-CODE-013")
        assert any(finding.rule_id == "PY-CODE-013" for finding in result.findings), (
            "str wrapper should produce a PY-CODE-013 finding"
        )

    def test_production_tuple_and_dict_wrappers_are_denied(self) -> None:
        code = (
            "def order_tuple(order_id: str) -> tuple[str]:\n"
            "    return tuple((order_id,))\n\n"
            "def order_dict(order_id: str) -> dict[str, str]:\n"
            "    return dict(order_id=order_id)\n"
        )
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/orders/cases.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        assert_denied_by(result, "PY-CODE-013")
        wrappers = {
            finding.metadata.get("function")
            for finding in result.findings
            if finding.rule_id == "PY-CODE-013"
        }
        assert wrappers == {"order_tuple", "order_dict"}


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
        assert_denied_by(result, "PY-CODE-014")
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
        assert_not_denied(result)
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
        assert_denied_by(result, "PY-CODE-015")
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
        assert_not_denied(result)
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
        assert_denied_by(result, "PY-CODE-016")
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
        assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-016" for finding in result.findings)
