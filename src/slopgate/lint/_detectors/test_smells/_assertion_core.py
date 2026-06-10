"""Detectors for test-specific smells."""

from __future__ import annotations

import ast


WEAK_ASSERT_NAMES = frozenset({"assertTrue", "assertIsNotNone"})
MOCK_FACTORY_NAMES = frozenset({"Mock", "MagicMock", "AsyncMock"})
MOCK_SETUP_NAMES = frozenset({"patch", "setattr"})
CALL_ONLY_MOCK_ASSERTS = frozenset(
    {
        "assert_called",
        "assert_called_once",
    }
)
SEMANTIC_MOCK_ASSERTS = frozenset(
    {
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_has_calls",
    }
)
INTEGRATION_NAME_TOKENS = ("e2e", "end_to_end", "integration", "pipeline")
PAYLOAD_TARGET_NAMES = frozenset(
    {
        "data",
        "event",
        "metadata",
        "payload",
        "response",
        "state",
    }
)
WEAK_TRUTHY_NAMES = PAYLOAD_TARGET_NAMES | {"success", "ok", "result"}
LOW_RISK_CAST_TARGET_TOKENS = frozenset(
    {
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
    }
)
HIGH_RISK_CAST_TARGET_SUFFIXES = (
    "Config",
    "Metadata",
    "Model",
    "Result",
    "Snapshot",
    "State",
)
HIGH_RISK_CAST_TARGET_TOKENS = frozenset(
    {
        "DetectionResult",
        "ExecutorGraphState",
        "GraphState",
        "JudgeGraphState",
        "JobMetadata",
        "OrchestrationState",
        "PlannerGraphState",
    }
)
DESERIALIZER_TEST_TOKENS = (
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
INTERNAL_SEAM_TOKENS = frozenset(
    {
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
    }
)
OUTER_BOUNDARY_PATCH_TOKENS = frozenset(
    {
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
    }
)
HIGH_RISK_NAMESPACE_KEYS = frozenset(
    {
        "company",
        "control_id",
        "field",
        "fields",
        "job_metadata",
        "metadata",
        "payload",
        "snapshot",
        "state",
    }
)


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def call_tail(call: ast.Call) -> str:
    return dotted_name(call.func).rsplit(".", maxsplit=1)[-1]


def iter_tests(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def is_none_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def is_true_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def is_zero_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == 0


def is_len_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
    )


def is_weak_compare(compare: ast.Compare) -> bool:
    if not compare.ops or not compare.comparators:
        return False
    right = compare.comparators[0]
    op = compare.ops[0]
    if isinstance(op, (ast.IsNot, ast.NotEq)) and is_none_constant(right):
        return True
    if isinstance(op, ast.Is) and is_true_constant(right):
        return True
    return (
        is_len_call(compare.left)
        and isinstance(op, (ast.Gt, ast.NotEq))
        and is_zero_constant(right)
    )


def is_call_only_mock_assert(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and call_tail(node) in CALL_ONLY_MOCK_ASSERTS:
        return True
    if not isinstance(node, ast.Assert):
        return False
    test = node.test
    if isinstance(test, ast.Attribute):
        return test.attr == "called"
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Attribute):
        return test.left.attr == "call_count"
    return False


def is_weak_assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        test = node.test
        if isinstance(test, ast.Compare):
            return is_weak_compare(test)
        if isinstance(test, ast.Name) and test.id.lower() in WEAK_TRUTHY_NAMES:
            return True
        if isinstance(test, ast.Call) and is_len_call(test):
            return True
    if isinstance(node, ast.Call):
        tail = call_tail(node)
        if tail in WEAK_ASSERT_NAMES:
            return True
    return False


def contains_mock_setup(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = dotted_name(child.func)
        tail = name.rsplit(".", maxsplit=1)[-1]
        if tail in MOCK_FACTORY_NAMES:
            return True
        if tail in MOCK_SETUP_NAMES and (
            tail == "patch" or name.startswith("monkeypatch.")
        ):
            return True
    return False


def has_semantic_assertion(test_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(test_node):
        if isinstance(child, ast.Call) and call_tail(child) in SEMANTIC_MOCK_ASSERTS:
            return True
        if isinstance(child, ast.Assert):
            if is_weak_assertion(child) or is_call_only_mock_assert(child):
                continue
            return True
    return False


def expr_preview(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__
