"""Extract persisted analysis facts from one parsed file."""

from __future__ import annotations

import ast

from slopgate.lint._helpers import ParsedFile
from slopgate.lint.project_index.facts import (
    BlockFact,
    CallSeqFact,
    CloneFact,
    FileAnalysisFacts,
    LiteralFact,
)
from slopgate.lint._detectors.test_smells import module_name_from_rel


def extract_file_facts(parsed: ParsedFile) -> FileAnalysisFacts:
    """Capture project and suite facts from one parsed Python file."""
    return FileAnalysisFacts(
        line_count=len(parsed.lines),
        module_name=module_name_from_rel(parsed.rel),
        semantic_clones=_semantic_clones(parsed),
        block_windows=_block_windows(parsed),
        call_sequences=_call_sequences(parsed),
        magic_numbers=_numeric_literals(parsed),
        string_literals=_textual_literals(parsed),
    )


def _semantic_clones(parsed: ParsedFile) -> tuple[CloneFact, ...]:
    from slopgate.lint.project_index.fact_filter import wanted_fact_type
    from slopgate.lint.project_index.facts import FACT_TYPE_CLONES

    if not wanted_fact_type(FACT_TYPE_CLONES):
        return ()
    from slopgate.lint._config import get_config
    from slopgate.lint._detectors.duplicates import (
        is_clone_candidate,
        normalize_ast,
        skip_docstring,
        structure_hash,
    )

    min_lines = get_config().min_function_body_lines
    facts: list[CloneFact] = []
    for node in ast.walk(parsed.tree):
        if not is_clone_candidate(node, min_lines):
            continue
        body = skip_docstring(node.body)
        if not body:
            continue
        canonical = "|".join(normalize_ast(stmt) for stmt in body)
        facts.append(CloneFact(structure_hash(canonical), node.name, node.lineno))
    return tuple(facts)


def _block_windows(parsed: ParsedFile) -> tuple[BlockFact, ...]:
    from slopgate.lint.project_index.fact_filter import wanted_fact_type
    from slopgate.lint.project_index.facts import FACT_TYPE_BLOCKS

    if not wanted_fact_type(FACT_TYPE_BLOCKS):
        return ()
    from slopgate.lint._detectors.duplicates import collect_block_windows

    groups = collect_block_windows([parsed])
    return tuple(
        BlockFact(digest=digest, scope=scope, start=start, end=end)
        for digest, members in groups.items()
        for _rel, scope, start, end in members
    )


def _call_sequences(parsed: ParsedFile) -> tuple[CallSeqFact, ...]:
    from slopgate.lint.project_index.fact_filter import wanted_fact_type
    from slopgate.lint.project_index.facts import FACT_TYPE_CALLS

    if not wanted_fact_type(FACT_TYPE_CALLS):
        return ()
    from slopgate.lint._config import get_config
    from slopgate.lint._detectors.duplicates import FUNC_TYPES, extract_call_sequence

    min_len = get_config().min_call_sequence_length
    facts: list[CallSeqFact] = []
    for node in ast.walk(parsed.tree):
        if not isinstance(node, FUNC_TYPES):
            continue
        sequence = extract_call_sequence(node)
        if len(sequence) >= min_len:
            facts.append(CallSeqFact(sequence, node.name, node.lineno))
    return tuple(facts)


def _numeric_literals(parsed: ParsedFile) -> tuple[LiteralFact, ...]:
    from slopgate.lint.project_index.fact_filter import wanted_fact_type
    from slopgate.lint.project_index.facts import FACT_TYPE_LITERALS

    if not wanted_fact_type(FACT_TYPE_LITERALS):
        return ()
    from slopgate.lint._detectors.duplicates import is_docstring_node

    facts: list[LiteralFact] = []
    for node in ast.walk(parsed.tree):
        if not isinstance(node, ast.Constant):
            continue
        if isinstance(node.value, bool) or is_docstring_node(node, parsed.parent_map):
            continue
        if isinstance(node.value, (int, float)):
            facts.append(LiteralFact(node.value, node.lineno))
    return tuple(facts)


def _textual_literals(parsed: ParsedFile) -> tuple[LiteralFact, ...]:
    from slopgate.lint.project_index.fact_filter import wanted_fact_type
    from slopgate.lint.project_index.facts import FACT_TYPE_LITERALS

    if not wanted_fact_type(FACT_TYPE_LITERALS):
        return ()
    from slopgate.lint._detectors.duplicates import (
        is_docstring_node,
        is_semantic_string_literal,
    )

    facts: list[LiteralFact] = []
    for node in ast.walk(parsed.tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if is_docstring_node(node, parsed.parent_map):
            continue
        if is_semantic_string_literal(node.value):
            facts.append(LiteralFact(node.value, node.lineno))
    return tuple(facts)
