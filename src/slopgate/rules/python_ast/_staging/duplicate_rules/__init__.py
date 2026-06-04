"""PY-DUP-001 through PY-DUP-004: Duplicate-code hook rules.

These rules port the lint-only duplicate detectors into reactive hooks so
that repeated code blocks, duplicate call sequences, semantic clones, and
repeated magic numbers are caught at write time, not just at lint time.

Staging: not yet registered in the rule registry.
"""

from __future__ import annotations

from slopgate.rules.python_ast._staging.duplicate_rules._blocks import PythonRepeatedBlocksRule
from slopgate.rules.python_ast._staging.duplicate_rules._call_sequences import PythonDuplicateCallSequenceRule
from slopgate.rules.python_ast._staging.duplicate_rules._magic_numbers import PythonRepeatedMagicNumberRule
from slopgate.rules.python_ast._staging.duplicate_rules._semantic import PythonSemanticCloneRule

__all__ = [
    "PythonDuplicateCallSequenceRule",
    "PythonRepeatedBlocksRule",
    "PythonRepeatedMagicNumberRule",
    "PythonSemanticCloneRule",
]
