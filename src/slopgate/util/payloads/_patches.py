from __future__ import annotations

_PATCH_PATH_PREFIXES = (
    "*** Update File: ",
    "*** Add File: ",
    "*** Delete File: ",
    "*** Move to: ",
    "+++ b/",
    "--- a/",
)


def _patch_path_from_line(line: str) -> str:
    for prefix in _PATCH_PATH_PREFIXES:
        if line.startswith(prefix):
            return line.replace(prefix, "", 1).strip()
    return ""


def parse_patch_candidate_paths(patch_blob: str) -> list[str]:
    paths: list[str] = []
    for line in patch_blob.splitlines():
        value = _patch_path_from_line(line)
        if value and value != "/dev/null" and value not in paths:
            paths.append(value)
    return paths


def extract_added_patch_content(patch_blob: str) -> str:
    added: list[str] = []
    for line in patch_blob.splitlines():
        if line.startswith("+++") or line.startswith("***"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    return "\n".join(added)


def _record_patch_content(
    contents: dict[str, list[str]], path: str, added: list[str]
) -> None:
    if path and added:
        contents.setdefault(path, []).extend(added)


def _render_patch_contents(contents: dict[str, list[str]]) -> list[tuple[str, str]]:
    return [(path, "\n".join(lines)) for path, lines in contents.items()]


def _parse_patch_contents(
    lines: list[str],
    path_prefixes: tuple[str, ...],
    reset_prefixes: tuple[str, ...],
) -> dict[str, list[str]]:
    contents: dict[str, list[str]] = {}
    active_path = ""
    added: list[str] = []
    for line in lines:
        if line.startswith(path_prefixes):
            _record_patch_content(contents, active_path, added)
            active_path, added = _patch_path_from_line(line), []
        elif line.startswith(reset_prefixes):
            _record_patch_content(contents, active_path, added)
            active_path, added = "", []
        elif active_path and line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    _record_patch_content(contents, active_path, added)
    return contents


def parse_patch_content_targets(patch_blob: str) -> list[tuple[str, str]]:
    """Return added content partitioned by the file section that owns it."""
    lines = patch_blob.splitlines()
    contents = _parse_patch_contents(
        lines,
        ("*** Add File: ", "*** Update File: "),
        ("*** End Patch",),
    )
    if not contents:
        contents = _parse_patch_contents(lines, ("+++ ",), ("diff --git ",))
    return _render_patch_contents(contents)
