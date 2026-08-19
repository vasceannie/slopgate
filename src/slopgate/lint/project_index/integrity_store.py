"""Persist and reload the assembled suite-integrity index."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from slopgate.lint._detectors.test_smells import IntegrityIndex, ProductionSymbol
from slopgate.lint.project_index.facts import SymbolFact
from slopgate.lint.project_index.models import ProjectIndex

_TABLE = "integrity_index"
_SINGLETON = "suite"


def index_content_signature(index: ProjectIndex) -> str:
    """Return a digest of persisted file paths and content hashes."""
    payload = "\n".join(
        f"{summary.relative_path}\0{summary.content_hash}" for summary in index.files
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_integrity_index(connection: sqlite3.Connection, index: ProjectIndex) -> None:
    """Store the assembled suite index keyed by the current file-hash signature."""
    from slopgate.lint.project_index.integrity_facts import integrity_index_from_project

    assembled = integrity_index_from_project(index)
    payload = _payload_from_index(assembled)
    connection.execute(
        f"""
        INSERT OR REPLACE INTO {_TABLE}(key, signature, payload_json)
        VALUES (?, ?, ?)
        """,
        (_SINGLETON, index_content_signature(index), json.dumps(payload, sort_keys=True)),
    )


def load_integrity_index(
    connection: sqlite3.Connection, index: ProjectIndex
) -> IntegrityIndex | None:
    """Return the stored suite index when the file-hash signature still matches."""
    row = connection.execute(
        f"SELECT signature, payload_json FROM {_TABLE} WHERE key = ?",
        (_SINGLETON,),
    ).fetchone()
    if row is None or str(row["signature"]) != index_content_signature(index):
        return None
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        return None
    return _index_from_payload(payload)


def load_or_build_integrity_index(index: ProjectIndex) -> IntegrityIndex:
    """Load the stored suite index, assembling from file facts on a miss."""
    from slopgate.lint.project_index.integrity_facts import integrity_index_from_project
    from slopgate.lint.project_index.store import connect_index

    connection = connect_index(index.root)
    try:
        stored = load_integrity_index(connection, index)
        if stored is not None:
            return stored
        assembled = integrity_index_from_project(index)
        return assembled
    finally:
        connection.close()


def _payload_from_index(assembled: IntegrityIndex) -> dict[str, object]:
    return {
        "production_symbols": [asdict(symbol) for symbol in assembled.production_symbols],
        "test_reference_tokens": sorted(assembled.test_reference_tokens),
        "test_reference_tokens_by_rel": {
            relative: sorted(tokens)
            for relative, tokens in sorted(assembled.test_reference_tokens_by_rel.items())
        },
        "integration_test_reference_tokens": sorted(
            assembled.integration_test_reference_tokens
        ),
        "production_call_sites": assembled.production_call_sites,
        "module_names": sorted(assembled.module_names),
        "hypothesis_reference_tokens": sorted(assembled.hypothesis_reference_tokens),
        "deprecated_symbols": [asdict(symbol) for symbol in assembled.deprecated_symbols],
    }


def _index_from_payload(payload: Mapping[str, object]) -> IntegrityIndex:
    symbols = _symbols_from_rows(payload.get("production_symbols"))
    deprecated = _symbols_from_rows(payload.get("deprecated_symbols"))
    return IntegrityIndex(
        parsed_src=[],
        parsed_tests=[],
        production_symbols=symbols,
        test_reference_tokens=_text_set(payload.get("test_reference_tokens")),
        test_reference_tokens_by_rel=_tokens_by_rel(
            payload.get("test_reference_tokens_by_rel")
        ),
        integration_test_reference_tokens=_text_set(
            payload.get("integration_test_reference_tokens")
        ),
        production_call_sites=_call_sites(payload.get("production_call_sites")),
        module_names=_text_set(payload.get("module_names")),
        hypothesis_reference_tokens=_text_set(
            payload.get("hypothesis_reference_tokens")
        ),
        deprecated_symbols=deprecated,
    )


def _symbols_from_rows(value: object) -> list[ProductionSymbol]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    copied: list[ProductionSymbol] = []
    for row in value:
        if not isinstance(row, Mapping):
            continue
        fact = SymbolFact.from_payload(row)
        copied.append(
            ProductionSymbol(
                name=fact.name,
                qualname=fact.qualname,
                module=fact.module,
                relative_path=fact.relative_path,
                lineno=fact.lineno,
                kind=fact.kind,
                parameter_count=fact.parameter_count,
                branch_score=fact.branch_score,
                transform_score=fact.transform_score,
                deprecated=fact.deprecated,
                replacement=fact.replacement,
            )
        )
    return copied


def _text_set(value: object) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {str(item) for item in value}


def _tokens_by_rel(value: object) -> dict[str, set[str]]:
    if not isinstance(value, Mapping):
        return {}
    return {str(relative): _text_set(tokens) for relative, tokens in value.items()}


def _call_sites(value: object) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    sites: dict[str, list[str]] = {}
    for name, locations in value.items():
        if not isinstance(locations, Sequence) or isinstance(locations, (str, bytes)):
            continue
        sites[str(name)] = [str(item) for item in locations]
    return sites
