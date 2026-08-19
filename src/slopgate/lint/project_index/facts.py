"""JSON-serializable per-file analysis facts for incremental aggregates."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

FACT_TYPE_CLONES = "clones"
FACT_TYPE_BLOCKS = "blocks"
FACT_TYPE_CALLS = "calls"
FACT_TYPE_LITERALS = "literals"
FACT_TYPE_INTEGRITY = "integrity"


def _text(payload: Mapping[str, object], key: str, missing: str | None = "") -> str | None:
    value = payload.get(key, missing)
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _count(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key, 0)
    return value if isinstance(value, int) else int(str(value))


def _mapping_rows(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(row for row in value if isinstance(row, Mapping))


@dataclass(frozen=True, slots=True)
class SymbolFact:
    """Persisted production symbol used by suite-integrity collectors."""

    name: str
    qualname: str
    module: str
    relative_path: str
    lineno: int
    kind: str
    parameter_count: int
    branch_score: int
    transform_score: int
    deprecated: bool
    replacement: str | None

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> SymbolFact:
        """Build a symbol fact from a stored JSON object."""
        return cls(
            name=_text(payload, "name") or "",
            qualname=_text(payload, "qualname") or "",
            module=_text(payload, "module") or "",
            relative_path=_text(payload, "relative_path") or "",
            lineno=_count(payload, "lineno"),
            kind=_text(payload, "kind") or "",
            parameter_count=_count(payload, "parameter_count"),
            branch_score=_count(payload, "branch_score"),
            transform_score=_count(payload, "transform_score"),
            deprecated=payload.get("deprecated") is True,
            replacement=_text(payload, "replacement", missing=None),
        )


@dataclass(frozen=True, slots=True)
class ImportNodeFact:
    """Persisted import used by stale-test-reference detection."""

    relative_path: str
    kind: str
    module: str
    names: tuple[str, ...]
    lineno: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> ImportNodeFact:
        """Build an import fact from a stored JSON object."""
        names = payload.get("names", ())
        name_values = names if isinstance(names, Sequence) else ()
        return cls(
            relative_path=_text(payload, "relative_path") or "",
            kind=_text(payload, "kind") or "",
            module=_text(payload, "module") or "",
            names=tuple(str(name) for name in name_values),
            lineno=_count(payload, "lineno"),
        )


@dataclass(frozen=True, slots=True)
class CloneFact:
    """Per-function semantic-clone fingerprint."""

    digest: str
    name: str
    lineno: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> CloneFact:
        """Build a clone fingerprint from a stored JSON object."""
        return cls(
            digest=_text(payload, "digest") or "",
            name=_text(payload, "name") or "",
            lineno=_count(payload, "lineno"),
        )


@dataclass(frozen=True, slots=True)
class BlockFact:
    """Per-file repeated-block window fingerprint."""

    digest: str
    scope: str
    start: int
    end: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> BlockFact:
        """Build a block-window fingerprint from a stored JSON object."""
        return cls(
            digest=_text(payload, "digest") or "",
            scope=_text(payload, "scope") or "",
            start=_count(payload, "start"),
            end=_count(payload, "end"),
        )


@dataclass(frozen=True, slots=True)
class CallSeqFact:
    """Per-function ordered call-sequence fingerprint."""

    sequence: tuple[str, ...]
    name: str
    lineno: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> CallSeqFact:
        """Build a call-sequence fingerprint from a stored JSON object."""
        sequence = payload.get("sequence", ())
        steps = sequence if isinstance(sequence, Sequence) else ()
        return cls(
            sequence=tuple(str(step) for step in steps),
            name=_text(payload, "name") or "",
            lineno=_count(payload, "lineno"),
        )


@dataclass(frozen=True, slots=True)
class LiteralFact:
    """One magic number or string literal occurrence."""

    value: int | float | str
    lineno: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> LiteralFact:
        """Build a literal occurrence from a stored JSON object."""
        value = payload.get("value", 0)
        if not isinstance(value, (int, float, str)) or isinstance(value, bool):
            value = str(value)
        return cls(value=value, lineno=_count(payload, "lineno"))


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


def _pair_tuple(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    pairs: list[tuple[str, str]] = []
    for item in value:
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) == 2:
            pairs.append((str(item[0]), str(item[1])))
    return tuple(pairs)


def facts_to_json(facts: FileAnalysisFacts) -> str:
    """Serialize file facts for the enrolled SQLite index."""
    return json.dumps(asdict(facts), sort_keys=True)


def facts_from_json(raw: str) -> FileAnalysisFacts:
    """Rehydrate file facts from a stored JSON payload."""
    payload = json.loads(raw) if raw else {}
    if not isinstance(payload, dict):
        return FileAnalysisFacts()
    return FileAnalysisFacts.from_payload(payload)


@dataclass(frozen=True, slots=True)
class FileAnalysisFacts:
    """Derived facts for one file, consumed by project and suite collectors."""

    line_count: int = 0
    module_name: str = ""
    production_symbols: tuple[SymbolFact, ...] = ()
    reference_tokens: tuple[str, ...] = ()
    integration_tokens: tuple[str, ...] = ()
    hypothesis_tokens: tuple[str, ...] = ()
    call_tails: tuple[tuple[str, str], ...] = ()
    import_nodes: tuple[ImportNodeFact, ...] = ()
    semantic_clones: tuple[CloneFact, ...] = ()
    block_windows: tuple[BlockFact, ...] = ()
    call_sequences: tuple[CallSeqFact, ...] = ()
    magic_numbers: tuple[LiteralFact, ...] = ()
    string_literals: tuple[LiteralFact, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> FileAnalysisFacts:
        """Build file facts from a stored JSON object."""
        return cls(
            line_count=_count(payload, "line_count"),
            module_name=_text(payload, "module_name") or "",
            production_symbols=tuple(
                SymbolFact.from_payload(row)
                for row in _mapping_rows(payload.get("production_symbols"))
            ),
            reference_tokens=_text_tuple(payload.get("reference_tokens")),
            integration_tokens=_text_tuple(payload.get("integration_tokens")),
            hypothesis_tokens=_text_tuple(payload.get("hypothesis_tokens")),
            call_tails=_pair_tuple(payload.get("call_tails")),
            import_nodes=tuple(
                ImportNodeFact.from_payload(row)
                for row in _mapping_rows(payload.get("import_nodes"))
            ),
            semantic_clones=tuple(
                CloneFact.from_payload(row)
                for row in _mapping_rows(payload.get("semantic_clones"))
            ),
            block_windows=tuple(
                BlockFact.from_payload(row)
                for row in _mapping_rows(payload.get("block_windows"))
            ),
            call_sequences=tuple(
                CallSeqFact.from_payload(row)
                for row in _mapping_rows(payload.get("call_sequences"))
            ),
            magic_numbers=tuple(
                LiteralFact.from_payload(row)
                for row in _mapping_rows(payload.get("magic_numbers"))
            ),
            string_literals=tuple(
                LiteralFact.from_payload(row)
                for row in _mapping_rows(payload.get("string_literals"))
            ),
        )
