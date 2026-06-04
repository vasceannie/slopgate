"""Detectors for test-specific smells."""

from __future__ import annotations

import ast


_WEAK_ASSERT_NAMES = frozenset({"assertTrue", "assertIsNotNone"})
_MOCK_FACTORY_NAMES = frozenset({"Mock", "MagicMock", "AsyncMock"})
_MOCK_SETUP_NAMES = frozenset({"patch", "setattr"})
_CALL_ONLY_MOCK_ASSERTS = frozenset({
    "assert_called",
    "assert_called_once",
})
_SEMANTIC_MOCK_ASSERTS = frozenset({
    "assert_called_with",
    "assert_called_once_with",
    "assert_any_call",
    "assert_has_calls",
})
_INTEGRATION_NAME_TOKENS = ("e2e", "end_to_end", "integration", "pipeline")
_PAYLOAD_TARGET_NAMES = frozenset({
    "data",
    "event",
    "metadata",
    "payload",
    "response",
    "state",
})
_WEAK_TRUTHY_NAMES = _PAYLOAD_TARGET_NAMES | {"success", "ok", "result"}
_LOW_RISK_CAST_TARGET_TOKENS = frozenset({
    "Any",
    "Dict",
    "Iterable",
    "JsonArray",
    "JsonObject",
    "JsonValue",
    "List",
    "Mapping",
    "MutableMapping",
    "MutableSequence",
    "Sequence",
    "TypedDict",
    "dict",
    "list",
    "object",
    "set",
    "tuple",
})
_HIGH_RISK_CAST_TARGET_SUFFIXES = (
    "Config",
    "Metadata",
    "Model",
    "Result",
    "Snapshot",
    "State",
)
_HIGH_RISK_CAST_TARGET_TOKENS = frozenset({
    "DetectionResult",
    "ExecutorGraphState",
    "GraphState",
    "JudgeGraphState",
    "JobMetadata",
    "OrchestrationState",
    "PlannerGraphState",
})
_DESERIALIZER_TEST_TOKENS = (
    "contract",
    "deserialize",
    "deserializer",
    "malformed",
    "parse",
    "parser",
    "schema",
    "unknown_fields",
    "wire",
)
_INTERNAL_SEAM_TOKENS = frozenset({
    "client",
    "enrich",
    "enrichment",
    "event_handler",
    "handler",
    "parser",
    "projection",
    "renderer",
    "screen",
    "serializer",
    "store",
    "widget",
})
_OUTER_BOUNDARY_PATCH_TOKENS = frozenset({
    "api",
    "bootstrap",
    "client_session",
    "datetime",
    "environ",
    "envvar",
    "external",
    "http",
    "module",
    "os.environ",
    "planner",
    "random",
    "requests",
    "subprocess",
    "sys.modules",
    "tempfile",
    "time",
    "uuid",
})
_HIGH_RISK_NAMESPACE_KEYS = frozenset({
    "company",
    "control_id",
    "field",
    "fields",
    "job_metadata",
    "metadata",
    "payload",
    "snapshot",
    "state",
})


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _call_tail(call: ast.Call) -> str:
    return _dotted_name(call.func).rsplit(".", maxsplit=1)[-1]


def _iter_tests(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _is_none_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_true_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_zero_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == 0


def _is_len_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
    )


def _is_weak_compare(compare: ast.Compare) -> bool:
    if not compare.ops or not compare.comparators:
        return False
    right = compare.comparators[0]
    op = compare.ops[0]
    if isinstance(op, (ast.IsNot, ast.NotEq)) and _is_none_constant(right):
        return True
    if isinstance(op, ast.Is) and _is_true_constant(right):
        return True
    return _is_len_call(compare.left) and isinstance(op, (ast.Gt, ast.NotEq)) and _is_zero_constant(right)


def _is_call_only_mock_assert(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and _call_tail(node) in _CALL_ONLY_MOCK_ASSERTS:
        return True
    if not isinstance(node, ast.Assert):
        return False
    test = node.test
    if isinstance(test, ast.Attribute):
        return test.attr == "called"
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Attribute):
        return test.left.attr == "call_count"
    return False


def _is_weak_assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        test = node.test
        if isinstance(test, ast.Compare):
            return _is_weak_compare(test)
        if isinstance(test, ast.Name) and test.id.lower() in _WEAK_TRUTHY_NAMES:
            return True
        if isinstance(test, ast.Call) and _is_len_call(test):
            return True
    if isinstance(node, ast.Call):
        tail = _call_tail(node)
        if tail in _WEAK_ASSERT_NAMES:
            return True
    return False


def _contains_mock_setup(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = _dotted_name(child.func)
        tail = name.rsplit(".", maxsplit=1)[-1]
        if tail in _MOCK_FACTORY_NAMES:
            return True
        if tail in _MOCK_SETUP_NAMES and (tail == "patch" or name.startswith("monkeypatch.")):
            return True
    return False


def _has_semantic_assertion(test_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(test_node):
        if isinstance(child, ast.Call) and _call_tail(child) in _SEMANTIC_MOCK_ASSERTS:
            return True
        if isinstance(child, ast.Assert):
            if _is_weak_assertion(child) or _is_call_only_mock_assert(child):
                continue
            return True
    return False


def _expr_preview(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__
