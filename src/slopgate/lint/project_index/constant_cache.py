"""Persist project constant-index facts in the enrolled lint store."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from slopgate.constants import METADATA_PATH
from slopgate.lint.project_index.write_lock import locked_index_connection
from slopgate.quality.constant_index import ConstantIndex, StringConstantMatch

_TABLE = "constant_index"
_SINGLETON = "constants"


def save_constant_index(root: Path, index: ConstantIndex) -> None:
    """Store extracted constants and the file stat signature used to reuse them."""
    from slopgate.config._repo import is_repo_enrolled

    if not is_repo_enrolled(root):
        return
    with locked_index_connection(root) as connection:
        connection.execute(
            f"""
            INSERT OR REPLACE INTO {_TABLE}(key, signature, payload_json)
            VALUES (?, ?, ?)
            """,
            (_SINGLETON, _file_signature(index.files), _payload_json(index)),
        )
        connection.commit()


def load_constant_index(root: Path, dirty: tuple[Path, ...]) -> ConstantIndex | None:
    """Return the stored constant index when candidate files are unchanged."""
    from slopgate.config._repo import is_repo_enrolled
    from slopgate.lint.project_index.store import connect_index
    from slopgate.quality.constant_index import is_constant_candidate_path

    if not is_repo_enrolled(root):
        return None
    if any(is_constant_candidate_path(path, root) for path in dirty):
        return None
    connection = connect_index(root)
    try:
        row = connection.execute(
            f"SELECT signature, payload_json FROM {_TABLE} WHERE key = ?",
            (_SINGLETON,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    index = _index_from_payload(root, str(row["payload_json"]))
    if index is None:
        return None
    if str(row["signature"]) != _file_signature(index.files):
        return None
    return index


def _file_signature(files: tuple[Path, ...]) -> str:
    parts: list[str] = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            return ""
        parts.append(f"{path.as_posix()}\0{stat.st_mtime_ns}\0{stat.st_size}")
    return "\n".join(parts)


def _payload_json(index: ConstantIndex) -> str:
    payload = {
        "files": [path.as_posix() for path in index.files],
        "string_constants": {
            value: [
                {
                    "name": match.name,
                    METADATA_PATH: match.path.as_posix(),
                    "lineno": match.lineno,
                }
                for match in matches
            ]
            for value, matches in index.string_constants.items()
        },
    }
    return json.dumps(payload, sort_keys=True)


def _index_from_payload(root: Path, raw: str) -> ConstantIndex | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    files = _paths_from_payload(payload.get("files"))
    constants = _constants_from_payload(payload.get("string_constants"))
    if files is None or constants is None:
        return None
    return ConstantIndex(root=root.resolve(), string_constants=constants, files=files)


def _paths_from_payload(value: object) -> tuple[Path, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    return tuple(Path(str(item)) for item in value)


def _constants_from_payload(
    value: object,
) -> dict[str, list[StringConstantMatch]] | None:
    if not isinstance(value, Mapping):
        return None
    collected: dict[str, list[StringConstantMatch]] = {}
    for raw_value, rows in value.items():
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            return None
        matches = _matches_from_rows(rows)
        if matches is None:
            return None
        collected[str(raw_value)] = matches
    return collected


def _matches_from_rows(rows: Sequence[object]) -> list[StringConstantMatch] | None:
    matches: list[StringConstantMatch] = []
    for row in rows:
        if not isinstance(row, Mapping):
            return None
        name = row.get("name")
        path = row.get(METADATA_PATH)
        lineno = row.get("lineno")
        if not isinstance(name, str) or not isinstance(path, str) or not isinstance(lineno, int):
            return None
        matches.append(StringConstantMatch(name=name, path=Path(path), lineno=lineno))
    return matches
