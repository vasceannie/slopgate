from __future__ import annotations

import ast

from slopgate.lint._helpers import class_body_lines, function_body_lines


def _module(source: str) -> ast.Module:
    return ast.parse(source)


def test_function_body_lines_skip_docstrings_and_include_multiline_body() -> None:
    tree = _module(
        "def target():\n"
        '    """doc"""\n'
        "    value = (\n"
        "        1 +\n"
        "        2\n"
        "    )\n"
        "    return value\n"
    )
    function = tree.body[0]

    assert isinstance(function, ast.FunctionDef)
    assert function_body_lines(function) == 5


def test_function_body_lines_return_zero_for_docstring_only_function() -> None:
    tree = _module('def target():\n    "doc only"\n')
    function = tree.body[0]

    assert isinstance(function, ast.FunctionDef)
    assert function_body_lines(function) == 0


def test_class_body_lines_include_direct_class_body_span() -> None:
    tree = _module(
        "class Target:\n"
        "    first = 1\n"
        "\n"
        "    def method(self):\n"
        "        return self.first\n"
    )
    class_node = tree.body[0]

    assert isinstance(class_node, ast.ClassDef)
    assert class_body_lines(class_node) == 4
