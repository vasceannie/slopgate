#!/usr/bin/env python3
"""Preserve or restore the required Headroom OpenCode transport-plugin tuple.

This file is the first-party source of truth for the installed reconciler
script. It preserves JSON and JSONC formatting and only inserts the exact
missing tuple. It never edits third-party Oh My OpenAgent files or package
caches.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.json"
BACKUP_ROOT = Path.home() / ".hermes" / "agent-config-steward" / "backups"
LOCK_PATH = Path(tempfile.gettempdir()) / "opencode-headroom-reconcile.lock"
PLUGIN_PATH = str(
    Path.home()
    / ".config"
    / "opencode"
    / "plugins"
    / "headroom"
    / "dist"
    / "entry.opencode.js"
)
PROXY_URL = "http://100.99.49.30:8787"
MAX_TCP_PORT = 65535
REQUIRED_ENTRY: list[object] = [PLUGIN_PATH, {"proxyUrl": PROXY_URL}]


class ReconcileError(RuntimeError):
    """A configuration state that must be repaired manually, not overwritten."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--backup-root", type=Path, default=BACKUP_ROOT)
    return parser.parse_args()


def skip_jsonc_trivia(source: str, index: int) -> int:
    """Advance past whitespace and JSONC comments without interpreting values."""
    while index < len(source):
        if source[index].isspace():
            index += 1
            continue
        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            return len(source) if newline < 0 else skip_jsonc_trivia(source, newline + 1)
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise ReconcileError("unterminated JSONC block comment")
            index = end + 2
            continue
        break
    return index


def _string_literal_end(source: str, opening: int) -> int:
    escaped = False
    cursor = opening + 1
    while cursor < len(source):
        char = source[cursor]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return cursor
        cursor += 1
    raise ReconcileError("unterminated JSON string")


def read_json_string(source: str, index: int) -> tuple[str, int]:
    """Return one JSON string literal and the first index after it."""
    if index >= len(source) or source[index] != '"':
        raise ReconcileError("expected JSON string")
    end = _string_literal_end(source, index)
    try:
        return json.loads(source[index : end + 1]), end + 1
    except json.JSONDecodeError as exc:
        raise ReconcileError("invalid JSON string literal") from exc

def find_matching_array_end(source: str, opening: int) -> int:
    depth = 0
    cursor = opening
    while cursor < len(source):
        cursor = skip_jsonc_trivia(source, cursor)
        if cursor >= len(source):
            break
        if source[cursor] == '"':
            _, cursor = read_json_string(source, cursor)
            continue
        if source[cursor] == "[":
            depth += 1
        elif source[cursor] == "]":
            depth -= 1
            if depth == 0:
                return cursor
        cursor += 1
    raise ReconcileError("unterminated plugin array")


def _plugin_value_array(source: str, after_key: int) -> int:
    """Return the plugin array start, or -1 when the key has no colon value."""
    value_start = skip_jsonc_trivia(source, after_key)
    if value_start >= len(source) or source[value_start] != ":":
        return -1
    array_start = skip_jsonc_trivia(source, value_start + 1)
    if array_start >= len(source) or source[array_start] != "[":
        raise ReconcileError("top-level plugin value is not an array")
    return array_start


def find_top_level_plugin_array(source: str) -> tuple[int, int]:
    """Locate the root-level plugin array while preserving source formatting."""
    depth = 0
    cursor = 0
    while cursor < len(source):
        cursor = skip_jsonc_trivia(source, cursor)
        if cursor >= len(source):
            break
        char = source[cursor]
        if char == '"':
            value, after_string = read_json_string(source, cursor)
            array_start = (
                _plugin_value_array(source, after_string)
                if depth == 1 and value == "plugin"
                else -1
            )
            if array_start >= 0:
                return array_start, find_matching_array_end(source, array_start)
            cursor = after_string
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        cursor += 1
    raise ReconcileError("top-level plugin array was not found")


def _advance_string_state(
    char: str, in_string: bool, escaped: bool
) -> tuple[bool, bool]:
    """Return the next (in_string, escaped) scanner state for one character."""
    if escaped:
        return in_string, False
    if char == "\\":
        return in_string, True
    if char == '"':
        return not in_string, False
    return in_string, escaped


def _blank_span(output: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if output[index] not in "\r\n":
            output[index] = " "


def _blank_jsonc_comments(source: str) -> str:
    """Replace JSONC comments with spaces, preserving line structure."""
    output = list(source)
    cursor = 0
    in_string = False
    escaped = False
    while cursor < len(source):
        char = source[cursor]
        if in_string or char == '"':
            in_string, escaped = _advance_string_state(char, in_string, escaped)
            cursor += 1
            continue
        if source.startswith("//", cursor):
            end = source.find("\n", cursor + 2)
            end = len(source) if end < 0 else end
            _blank_span(output, cursor, end)
            cursor = end
            continue
        if source.startswith("/*", cursor):
            end = source.find("*/", cursor + 2)
            if end < 0:
                raise ReconcileError("unterminated JSONC block comment")
            _blank_span(output, cursor, end + 2)
            cursor = end + 2
            continue
        cursor += 1
    return "".join(output)


def _next_significant_index(source: str, start: int) -> int:
    lookahead = start
    while lookahead < len(source) and source[lookahead].isspace():
        lookahead += 1
    return lookahead


def _remove_trailing_commas(source: str) -> str:
    """Blank commas directly preceding ``}`` or ``]`` outside strings."""
    output = list(source)
    cursor = 0
    in_string = False
    escaped = False
    while cursor < len(source):
        char = source[cursor]
        if in_string or char == '"':
            in_string, escaped = _advance_string_state(char, in_string, escaped)
        elif char == ",":
            lookahead = _next_significant_index(source, cursor + 1)
            if lookahead < len(source) and source[lookahead] in "}]":
                output[cursor] = " "
        cursor += 1
    return "".join(output)


def jsonc_to_json(source: str) -> str:
    """Remove JSONC comments and trailing commas without changing string values."""
    return _remove_trailing_commas(_blank_jsonc_comments(source))


def _unique_object(pairs: Iterable[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReconcileError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ReconcileError(f"invalid JSON constant: {value}")


def parse_jsonc_document(source: str) -> dict[str, object]:
    try:
        parsed = json.loads(
            jsonc_to_json(source),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ReconcileError(f"invalid JSON/JSONC: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ReconcileError("top-level config value is not an object")
    return cast(dict[str, object], parsed)


def _contains_plugin_path(value: object) -> bool:
    if value == PLUGIN_PATH:
        return True
    if isinstance(value, list):
        items = cast(list[object], value)
        return any(_contains_plugin_path(item) for item in items)
    if isinstance(value, dict):
        items = cast(dict[object, object], value)
        return any(
            _contains_plugin_path(key) or _contains_plugin_path(item)
            for key, item in items.items()
        )
    return False


def is_valid_proxy_url(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    return port is None or 1 <= port <= MAX_TCP_PORT


def classify_plugin_entries(plugin_entries: list[object]) -> str:
    candidates: list[list[object]] = []
    for entry in plugin_entries:
        if isinstance(entry, list):
            candidate = cast(list[object], entry)
            if candidate and candidate[0] == PLUGIN_PATH:
                candidates.append(candidate)
                continue
        if _contains_plugin_path(cast(object, entry)):
            raise ReconcileError("ambiguous Headroom plugin path reference")

    if not candidates:
        return "missing"
    if len(candidates) != 1:
        raise ReconcileError("duplicate Headroom plugin entries")

    candidate = candidates[0]
    if len(candidate) != 2 or not isinstance(candidate[1], dict):
        raise ReconcileError("malformed Headroom plugin tuple")
    options = cast(dict[str, object], candidate[1])
    proxy_url = options.get("proxyUrl")
    if not is_valid_proxy_url(proxy_url):
        raise ReconcileError("Headroom proxyUrl is not a valid HTTP(S) URL")
    return "already-present" if proxy_url == PROXY_URL else "preserved-local-override"


def render_plugin_entry(source: str, array_start: int) -> str:
    """Insert the required tuple as the first entry, preserving source formatting."""
    line_start = source.rfind("\n", 0, array_start) + 1
    line = source[line_start:array_start]
    key_indent = line[: len(line) - len(line.lstrip(" \t"))]
    entry_indent = key_indent + "  "
    rendered = json.dumps(REQUIRED_ENTRY, indent=2, ensure_ascii=False)
    entry = "\n".join(entry_indent + line for line in rendered.splitlines())
    next_value = skip_jsonc_trivia(source, array_start + 1)
    separator = "" if next_value < len(source) and source[next_value] == "]" else ","
    return (
        source[: array_start + 1]
        + "\n"
        + entry
        + separator
        + source[array_start + 1 :]
    )


def inspect_config(source: str) -> tuple[str, int, int]:
    document = parse_jsonc_document(source)
    plugin_entries = document.get("plugin")
    if not isinstance(plugin_entries, list):
        raise ReconcileError("top-level plugin value is not an array")
    array_start, array_end = find_top_level_plugin_array(source)
    return classify_plugin_entries(cast(list[object], plugin_entries)), array_start, array_end


def _sync_parent_directory(config_path: Path) -> None:
    directory_fd = os.open(config_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _atomic_write(config_path: Path, updated: str) -> None:
    if config_path.is_symlink():
        raise ReconcileError("config is a symlink; reconcile its resolved target manually")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{config_path.name}.", suffix=".tmp", dir=config_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, config_path.stat().st_mode)
        os.replace(temporary, config_path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _backup_and_write(config_path: Path, updated: str, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_path = backup_dir / config_path.name
    shutil.copy2(config_path, backup_path)
    _atomic_write(config_path, updated)
    _sync_parent_directory(config_path)
    return backup_path


def reconcile(config_path: Path, backup_root: Path) -> tuple[str, Path | None]:
    if config_path.is_symlink():
        raise ReconcileError("config is a symlink; reconcile its resolved target manually")
    try:
        original = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReconcileError(f"cannot read config: {exc}") from exc

    status, array_start, _ = inspect_config(original)
    if status != "missing":
        return status, None

    updated = render_plugin_entry(original, array_start)
    repaired_status, _, _ = inspect_config(updated)
    if repaired_status != "already-present":
        raise ReconcileError("post-write verification of Headroom tuple failed")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = backup_root / f"headroom-reconcile-{stamp}"
    try:
        backup_path = _backup_and_write(config_path, updated, backup_dir)
    except OSError as exc:
        raise ReconcileError(f"could not atomically reconcile config: {exc}") from exc

    return "repaired", backup_path


def main() -> int:
    args = parse_args()
    with LOCK_PATH.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            status, backup_path = reconcile(args.config, args.backup_root)
        except ReconcileError as exc:
            print(f"headroom-reconcile status=refused reason={exc}", file=sys.stderr)
            return 1
    suffix = f" backup={backup_path}" if backup_path else ""
    print(f"headroom-reconcile status={status} config={args.config}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
