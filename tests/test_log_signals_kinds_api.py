"""Contract for log-signal classifiers and private-name aliases."""

from __future__ import annotations

import ast
import sys

from slopgate.rules.python_ast._rules.compat import install_private_module_aliases
from slopgate.rules.python_ast._rules.log_signals.kinds import (
    boundary_kind_for_function,
    class_name_has_package_boundary_signal,
    contains_package_boundary_call,
    iter_public_boundary_functions,
)

CLIENT_CLASS = "OrdersClient"
ADAPTER_PATH = "src/adapters/orders.py"
AST_HEALTH_ALIAS = "slopgate.rules.python_ast._rules._ast_health"


def test_class_name_has_package_boundary_signal_accepts_client_suffix() -> None:
    matched = class_name_has_package_boundary_signal(CLIENT_CLASS)
    assert (CLIENT_CLASS, matched) == (CLIENT_CLASS, True)


def test_class_name_has_package_boundary_signal_rejects_none() -> None:
    matched = class_name_has_package_boundary_signal(None)
    assert (None, matched) == (None, False)


def test_contains_package_boundary_call_detects_client_get() -> None:
    module = ast.parse("client.get('/v1/orders')")
    matched = contains_package_boundary_call(module)
    assert (ast.dump(module.body[0]), matched) == (
        ast.dump(ast.parse("client.get('/v1/orders')").body[0]),
        True,
    )


def test_boundary_kind_for_function_marks_adapter_path() -> None:
    node = ast.parse("def send_order():\n    pass\n").body[0]
    assert isinstance(node, ast.FunctionDef)
    kind = boundary_kind_for_function(ADAPTER_PATH, node, None)
    assert kind == "package boundary", kind


def test_iter_public_boundary_functions_skips_dunder() -> None:
    module = ast.parse("def __len__(self):\n    return 1\n\ndef export():\n    pass\n")
    found = iter_public_boundary_functions(module.body)
    names = [node.name for node, _cls in found]
    assert names == ["export"], found


def test_install_private_module_aliases_registers_ast_health() -> None:
    install_private_module_aliases()
    assert AST_HEALTH_ALIAS in sys.modules, AST_HEALTH_ALIAS
