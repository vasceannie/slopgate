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
