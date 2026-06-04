"""Duplicate-rule test cases."""

from __future__ import annotations

from slopgate.rules.base import Rule
from slopgate.rules.python_ast._staging.duplicate_rules import (
    PythonDuplicateCallSequenceRule,
    PythonRepeatedBlocksRule,
    PythonRepeatedMagicNumberRule,
    PythonSemanticCloneRule,
)

RuleType = type[Rule]

_DUPLICATE_RULE_CASES: tuple[tuple[str, RuleType, bool, str], ...] = (
    (
        "repeated_blocks_clean_single_block",
        PythonRepeatedBlocksRule,
        False,
        """\
        def foo():
            x = 1
            y = 2
            z = 3
            return x + y + z
        """,
    ),
    (
        "repeated_blocks_detects_copy_paste",
        PythonRepeatedBlocksRule,
        True,
        """\
        def foo():
            x = fetch_data()
            y = transform(x)
            z = validate(y)

        def bar():
            x = fetch_data()
            y = transform(x)
            z = validate(y)
        """,
    ),
    (
        "repeated_blocks_ignores_import_only",
        PythonRepeatedBlocksRule,
        False,
        """\
        import os
        import sys
        import json
        """,
    ),
    (
        "repeated_blocks_ignores_module_preamble",
        PythonRepeatedBlocksRule,
        False,
        '''\
        """Module docs."""
        from __future__ import annotations
        import os
        import sys

        value = compute_result(data)
        total = value + 1
        emit(total)
        ''',
    ),
    (
        "repeated_blocks_different_logic",
        PythonRepeatedBlocksRule,
        False,
        """\
        def foo():
            x = 1
            y = 2
            z = 3

        def bar():
            a = "hello"
            b = "world"
            c = "!"
        """,
    ),
    (
        "repeated_blocks_real_duplicates_after_preamble",
        PythonRepeatedBlocksRule,
        True,
        """\
        import os
        import sys

        def first():
            data = load_items()
            normalized = normalize(data)
            return persist(normalized)

        def second():
            payload = load_items()
            cleaned = normalize(payload)
            return persist(cleaned)
        """,
    ),
    (
        "duplicate_calls_short_sequence",
        PythonDuplicateCallSequenceRule,
        False,
        """\
        def foo():
            read()
            parse()

        def bar():
            read()
            parse()
        """,
    ),
    (
        "duplicate_calls_detects_sequence",
        PythonDuplicateCallSequenceRule,
        True,
        """\
        def foo():
            read()
            parse()
            validate()
            save()

        def bar():
            read()
            parse()
            validate()
            save()
        """,
    ),
    (
        "duplicate_calls_different_order",
        PythonDuplicateCallSequenceRule,
        False,
        """\
        def foo():
            read()
            parse()
            validate()

        def bar():
            validate()
            parse()
            read()
        """,
    ),
    (
        "semantic_clone_detects_parametric_copy",
        PythonSemanticCloneRule,
        True,
        """\
        def process_user():
            data = fetch()
            result = transform(data)
            store(result)
            return result

        def process_order():
            items = fetch()
            output = transform(items)
            store(output)
            return output
        """,
    ),
    (
        "semantic_clone_different_structure",
        PythonSemanticCloneRule,
        False,
        """\
        def process_user():
            data = fetch()
            return data

        def process_order():
            for item in items:
                handle(item)
            return True
        """,
    ),
    (
        "semantic_clone_ignores_dunder",
        PythonSemanticCloneRule,
        False,
        """\
        def __init__(self):
            self.x = 1
            self.y = 2
            self.z = 3

        def __repr__(self):
            self.x = 1
            self.y = 2
            self.z = 3
        """,
    ),
    (
        "magic_numbers_common_values",
        PythonRepeatedMagicNumberRule,
        False,
        """\
        x = 0
        y = 1
        z = -1
        w = 2
        a = 0
        b = 1
        c = 2
        """,
    ),
    (
        "magic_numbers_detects_repetition",
        PythonRepeatedMagicNumberRule,
        True,
        """\
        x = 42
        y = 42
        z = 42
        w = 42
        """,
    ),
    ("magic_numbers_at_threshold", PythonRepeatedMagicNumberRule, False, "x = 42\ny = 42\nz = 42"),
    (
        "magic_numbers_ignores_docstrings",
        PythonRepeatedMagicNumberRule,
        False,
        '"""The answer is 42, or maybe 42, definitely 42."""',
    ),
)
