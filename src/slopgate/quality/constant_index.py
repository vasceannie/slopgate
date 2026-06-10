"""Shared project-level index of string constants for quality checks."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

KNOWN_CONSTANT_GLOBS: tuple[str, ...] = (
    "constants.py",
    "config.py",
    "settings.py",
    "defaults.py",
    "*_constants.py",
    "config/*.py",
)

_DEFAULT_MAX_FILE_SIZE = 128_000


@dataclass(frozen=True, slots=True)
class StringConstantMatch:
    """A discovered module-level string constant definition."""

    name: str
    path: Path
    lineno: int


@dataclass(frozen=True, slots=True)
class ConstantIndex:
    """Index of project constants discovered from bounded file scans."""

    root: Path
    string_constants: dict[str, list[StringConstantMatch]]
    files: tuple[Path, ...]

    def find_string_constant(self, value: str) -> StringConstantMatch | None:
        matches = self.string_constants.get(value)
        if not matches:
            return None
        return matches[0]

    def first_constants_file(self) -> Path | None:
        if not self.files:
            return None
        return self.files[0]


_FILE_CACHE: dict[Path, tuple[int, int, dict[str, list[StringConstantMatch]]]] = {}
_session_index: ConstantIndex | None = None


def set_session_constant_index(index: ConstantIndex) -> None:
    global _session_index
    _session_index = index


def get_session_constant_index() -> ConstantIndex | None:
    return _session_index


def iter_constant_candidate_paths(
    root: Path, patterns: tuple[str, ...] = KNOWN_CONSTANT_GLOBS
) -> list[Path]:
    """Return sorted, de-duplicated constant/config module candidates."""

    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for candidate in root.rglob(pattern):
            if not candidate.is_file() or candidate in seen:
                continue
            seen.add(candidate)
            found.append(candidate)
    return sorted(found)


def _extract_string_constants(path: Path) -> dict[str, list[StringConstantMatch]]:
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    constants: dict[str, list[StringConstantMatch]] = {}
    for node in tree.body:
        target_name: str | None = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value
        if (
            target_name is None
            or value_node is None
            or not target_name.isupper()
            or not isinstance(value_node, ast.Constant)
            or not isinstance(value_node.value, str)
        ):
            continue
        value = value_node.value
        match = StringConstantMatch(
            name=target_name,
            path=path,
            lineno=getattr(node, "lineno", 1),
        )
        constants.setdefault(value, []).append(match)
    return constants


def _merge_constants(
    target: dict[str, list[StringConstantMatch]],
    incoming: dict[str, list[StringConstantMatch]],
) -> None:
    for value, matches in incoming.items():
        target.setdefault(value, []).extend(matches)


def _cached_constants_for(
    candidate: Path,
    *,
    stat_size: int,
    stat_mtime_ns: int,
    use_mtime_cache: bool,
) -> dict[str, list[StringConstantMatch]] | None:
    if not use_mtime_cache:
        return None
    cache_entry = _FILE_CACHE.get(candidate)
    if cache_entry is None:
        return None
    cached_mtime, cached_size, cached_values = cache_entry
    if cached_mtime == stat_mtime_ns and cached_size == stat_size:
        return cached_values
    return None


def _extract_constants_with_cache(
    candidate: Path,
    *,
    stat_size: int,
    stat_mtime_ns: int,
    use_mtime_cache: bool,
) -> dict[str, list[StringConstantMatch]] | None:
    cached = _cached_constants_for(
        candidate,
        stat_size=stat_size,
        stat_mtime_ns=stat_mtime_ns,
        use_mtime_cache=use_mtime_cache,
    )
    if cached is not None:
        return cached
    try:
        extracted = _extract_string_constants(candidate)
    except (OSError, SyntaxError, UnicodeError):
        return None
    if use_mtime_cache:
        _FILE_CACHE[candidate] = (stat_mtime_ns, stat_size, extracted)
    return extracted


def _sort_constant_matches(collected: dict[str, list[StringConstantMatch]]) -> None:
    for matches in collected.values():
        matches.sort(key=lambda m: (str(m.path), m.lineno, m.name))


def build_project_constant_index(
    root: Path,
    *,
    max_file_size: int | None = _DEFAULT_MAX_FILE_SIZE,
    use_mtime_cache: bool = True,
) -> ConstantIndex:
    """Build a bounded project-level constant index.

    Scans only known config/constant filename patterns. Individual file reads can
    be bounded with ``max_file_size``. If ``use_mtime_cache`` is enabled, file-level
    extracted constants are reused until file mtime/size changes.
    """

    root = root.resolve()
    collected: dict[str, list[StringConstantMatch]] = {}
    files: list[Path] = []
    for candidate in iter_constant_candidate_paths(root):
        try:
            stat = candidate.stat()
        except OSError:
            continue
        if max_file_size is not None and stat.st_size > max_file_size:
            continue
        extracted = _extract_constants_with_cache(
            candidate,
            stat_size=stat.st_size,
            stat_mtime_ns=stat.st_mtime_ns,
            use_mtime_cache=use_mtime_cache,
        )
        if extracted is None:
            continue
        _merge_constants(collected, extracted)
        files.append(candidate)

    _sort_constant_matches(collected)
    return ConstantIndex(root=root, string_constants=collected, files=tuple(files))


def find_string_constant(
    value: str, *, root: Path | None = None
) -> StringConstantMatch | None:
    """Find a string constant by value from the active/session index."""

    index = get_session_constant_index()
    if index is None:
        if root is None:
            return None
        index = build_project_constant_index(root)
        set_session_constant_index(index)
    return index.find_string_constant(value)


def suggest_constant_name(value: str) -> str:
    """Build a stable, uppercase candidate constant name from a string value."""

    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value.strip())
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", spaced).strip("_").upper()
    if not cleaned:
        return "EXTRACTED_STRING"
    if cleaned[0].isdigit():
        cleaned = f"STR_{cleaned}"
    return cleaned[:48]
