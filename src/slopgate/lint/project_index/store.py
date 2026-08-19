"""SQLite persistence for enrolled-repo lint file facts."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from slopgate.constants import (
    LINT_CACHE_DIRNAME,
    LINT_INDEX_FILENAME,
    LINT_INDEX_SCHEMA_VERSION,
    LINT_SQLITE_TIMEOUT_SECONDS,
)
from slopgate.lint._baseline import Violation
from slopgate.lint.project_index.facts import facts_from_json, facts_to_json
from slopgate.lint.project_index.fingerprint import engine_fingerprint
from slopgate.lint.project_index.models import ProjectFileSummary

_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""
_CREATE_FILES = """
CREATE TABLE IF NOT EXISTS files (
    relative_path TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    symbols_json TEXT NOT NULL,
    imports_json TEXT NOT NULL,
    duplicate_fingerprint TEXT NOT NULL,
    facts_json TEXT NOT NULL
)
"""
_CREATE_VIOLATIONS = """
CREATE TABLE IF NOT EXISTS file_violations (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    collector_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    identifier TEXT NOT NULL,
    detail TEXT NOT NULL,
    metadata_json TEXT NOT NULL
)
"""
_INDEX_VIOLATIONS = """
CREATE INDEX IF NOT EXISTS file_violations_collector_path
ON file_violations(collector_id, relative_path)
"""
_CREATE_INTEGRITY = """
CREATE TABLE IF NOT EXISTS integrity_index (
    key TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""
_CREATE_CONSTANTS = """
CREATE TABLE IF NOT EXISTS constant_index (
    key TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""
_META_SCHEMA = "schema_version"
_META_FINGERPRINT = "engine_fingerprint"
_FILE_LOCAL_READY = "1"


def index_db_path(root: Path) -> Path:
    """Return the enrolled-repo lint fact database path."""
    return root / LINT_CACHE_DIRNAME / LINT_INDEX_FILENAME


def connect_index(root: Path) -> sqlite3.Connection:
    """Open (and initialize) the enrolled lint fact database."""
    path = index_db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=LINT_SQLITE_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    _initialize_schema(connection)
    return connection


def store_matches_engine(connection: sqlite3.Connection, root: Path) -> bool:
    """Return True when persisted fingerprint matches the current engine."""
    fingerprint = engine_fingerprint(root)
    rows = dict(connection.execute("SELECT key, value FROM meta").fetchall())
    return (
        rows.get(_META_SCHEMA) == str(LINT_INDEX_SCHEMA_VERSION)
        and rows.get(_META_FINGERPRINT) == fingerprint
    )


def reset_store(connection: sqlite3.Connection, root: Path) -> None:
    """Drop persisted facts after an engine or schema mismatch."""
    _apply_sql(
        connection,
        (
            "DROP TABLE IF EXISTS files",
            "DROP TABLE IF EXISTS file_violations",
            "DROP TABLE IF EXISTS integrity_index",
            "DROP TABLE IF EXISTS constant_index",
            "DELETE FROM meta",
        ),
    )
    _initialize_schema(connection)
    for key, value in (
        (_META_SCHEMA, str(LINT_INDEX_SCHEMA_VERSION)),
        (_META_FINGERPRINT, engine_fingerprint(root)),
    ):
        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (key, value),
        )
    connection.commit()


def load_file_rows(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Return persisted file rows keyed by relative path."""
    return {
        str(row["relative_path"]): row
        for row in connection.execute("SELECT * FROM files")
    }


def upsert_file(connection: sqlite3.Connection, summary: ProjectFileSummary) -> None:
    """Insert or replace one file summary."""
    connection.execute(
        """
        INSERT OR REPLACE INTO files(
            relative_path, kind, size, mtime_ns, content_hash,
            symbols_json, imports_json, duplicate_fingerprint, facts_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary.relative_path,
            summary.kind,
            summary.size,
            summary.mtime_ns,
            summary.content_hash,
            json.dumps(list(summary.symbols)),
            json.dumps(list(summary.imports)),
            summary.duplicate_fingerprint,
            facts_to_json(summary.facts),
        ),
    )


def delete_files(connection: sqlite3.Connection, relative_paths: Sequence[str]) -> None:
    """Remove deleted files from the fact database."""
    rows = [(relative,) for relative in relative_paths]
    connection.executemany("DELETE FROM files WHERE relative_path = ?", rows)
    connection.executemany(
        "DELETE FROM file_violations WHERE relative_path = ?", rows
    )


def summary_from_row(root: Path, row: sqlite3.Row) -> ProjectFileSummary:
    """Rehydrate a file summary from a persisted row."""
    relative = str(row["relative_path"])
    return ProjectFileSummary(
        path=root / relative,
        relative_path=relative,
        kind=str(row["kind"]),
        size=int(row["size"]),
        mtime_ns=int(row["mtime_ns"]),
        content_hash=str(row["content_hash"]),
        symbols=tuple(json.loads(str(row["symbols_json"]))),
        imports=tuple(json.loads(str(row["imports_json"]))),
        duplicate_fingerprint=str(row["duplicate_fingerprint"]),
        facts=facts_from_json(str(row["facts_json"])),
    )


def load_violations_for_hashes(
    connection: sqlite3.Connection,
    collector_id: str,
    content_hashes: tuple[str, ...],
) -> list[Violation]:
    """Return cached file-local violations for one collector across relative paths."""
    from slopgate.constants import LINT_SQLITE_IN_CHUNK

    if not content_hashes:
        return []
    violations: list[Violation] = []
    for start in range(0, len(content_hashes), LINT_SQLITE_IN_CHUNK):
        chunk = content_hashes[start : start + LINT_SQLITE_IN_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = connection.execute(
            f"""
            SELECT relative_path, identifier, detail, metadata_json
            FROM file_violations
            WHERE collector_id = ? AND relative_path IN ({placeholders})
            """,
            (collector_id, *chunk),
        ).fetchall()
        violations.extend(_violations_from_rows(collector_id, rows))
    return violations


def _violations_from_rows(collector_id: str, rows: Sequence[sqlite3.Row]) -> list[Violation]:
    return [
        Violation(
            rule=collector_id,
            relative_path=str(row["relative_path"]),
            identifier=str(row["identifier"]),
            detail=str(row["detail"]),
            metadata=json.loads(str(row["metadata_json"])),
        )
        for row in rows
    ]


def is_file_local_ready(connection: sqlite3.Connection) -> bool:
    """Return True when a complete file-local violation cache has been stored."""
    from slopgate.constants import LINT_INDEX_FILE_LOCAL_READY_KEY

    return meta_value(connection, LINT_INDEX_FILE_LOCAL_READY_KEY) == _FILE_LOCAL_READY


def meta_value(connection: sqlite3.Connection, key: str) -> str | None:
    """Return one persisted index metadata value."""
    row = connection.execute(
        "SELECT value FROM meta WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row is not None else None


def mark_file_local_ready(connection: sqlite3.Connection) -> None:
    """Record that file-local violations have been fully persisted."""
    from slopgate.constants import LINT_INDEX_FILE_LOCAL_READY_KEY

    connection.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        (LINT_INDEX_FILE_LOCAL_READY_KEY, _FILE_LOCAL_READY),
    )


def load_cached_collector_results(
    connection: sqlite3.Connection, collector_ids: frozenset[str]
) -> list[tuple[str, list[Violation]]]:
    """Replay persisted violations for a clean warm run."""
    results: list[tuple[str, list[Violation]]] = []
    for collector_id in sorted(collector_ids):
        rows = connection.execute(
            """
            SELECT relative_path, identifier, detail, metadata_json
            FROM file_violations
            WHERE collector_id = ?
            """,
            (collector_id,),
        ).fetchall()
        results.append((collector_id, _violations_from_rows(collector_id, rows)))
    return results


def replace_file_violations(
    connection: sqlite3.Connection,
    collector_id: str,
    target: tuple[str, str] | None,
    violations: Sequence[Violation],
) -> None:
    """Replace cached violations for one collector, optionally limited to one path."""
    if target is None:
        content_hash = ""
        connection.execute(
            "DELETE FROM file_violations WHERE collector_id = ?",
            (collector_id,),
        )
    else:
        content_hash, relative_path = target
        connection.execute(
            "DELETE FROM file_violations WHERE collector_id = ? AND relative_path = ?",
            (collector_id, relative_path),
        )
    connection.executemany(
        """
        INSERT INTO file_violations(
            content_hash, collector_id, relative_path, identifier, detail, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                content_hash,
                collector_id,
                violation.relative_path,
                violation.identifier,
                violation.detail,
                json.dumps(violation.metadata, sort_keys=True, default=str),
            )
            for violation in violations
        ],
    )


def _apply_sql(connection: sqlite3.Connection, statements: tuple[str, ...]) -> None:
    """Run schema statements in order."""
    for statement in statements:
        connection.execute(statement)


def _initialize_schema(connection: sqlite3.Connection) -> None:
    _apply_sql(
        connection,
        (_CREATE_META, _CREATE_FILES, _CREATE_VIOLATIONS, _INDEX_VIOLATIONS, _CREATE_INTEGRITY, _CREATE_CONSTANTS),
    )
    connection.commit()
