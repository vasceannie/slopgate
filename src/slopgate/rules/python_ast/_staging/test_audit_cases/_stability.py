"""Stability cases for staging hook rules."""

from __future__ import annotations

from vibeforcer.constants import MAX_PARAMS
from vibeforcer.rules.base import Rule
from vibeforcer.rules.python_ast._staging.duplicate_rules import (
    PythonDuplicateCallSequenceRule,
    PythonRepeatedBlocksRule,
    PythonRepeatedMagicNumberRule,
    PythonSemanticCloneRule,
)
from vibeforcer.rules.python_ast._staging.test_smell_rules import (
    PythonAssertionRouletteRule,
    PythonConditionalAssertionRule,
    PythonEagerTestRule,
    PythonFixtureOutsideConftestRule,
)

RuleType = type[Rule]
_DEEP_NESTING_DEPTH = MAX_PARAMS * (MAX_PARAMS + 1)

_ALL_STAGING_RULES: tuple[RuleType, ...] = (
    PythonRepeatedBlocksRule,
    PythonDuplicateCallSequenceRule,
    PythonSemanticCloneRule,
    PythonRepeatedMagicNumberRule,
    PythonEagerTestRule,
    PythonAssertionRouletteRule,
    PythonFixtureOutsideConftestRule,
    PythonConditionalAssertionRule,
)

_STABILITY_SOURCES: tuple[tuple[str, str], ...] = (
    ("empty_file", ""),
    ("syntax_error", "def foo(:\n    pass"),
    ("binary_garbage", "\x00\x01\x02\xff"),
    ("very_long_line", "x = " + "1 + " * 10000 + "1"),
    (
        "deeply_nested",
        "def f():\n" + "".join(
            "    " * (depth + 1) + "if True:\n" for depth in range(_DEEP_NESTING_DEPTH)
        ),
    ),
    ("unicode", '# 文件\nx = "日本語"\n'),
    ("massive_file", "x = 1\n" * 100000),
)
