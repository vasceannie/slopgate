from __future__ import annotations

from slopgate._types import object_dict, object_list, string_value
from slopgate.constants import METADATA_PATH
from slopgate.util.path_filters import is_third_party_or_virtualenv_path

NON_FINAL_METADATA_PATHS = frozenset({"content", "patch.diff"})


def quality_metadata_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    normalized = path_value.replace("\\", "/")
    if normalized.lower() in NON_FINAL_METADATA_PATHS:
        return None
    if is_third_party_or_virtualenv_path(normalized):
        return None
    return path_value


def _metadata_hit_path(hit: object) -> str | None:
    if isinstance(hit, str):
        return hit
    return string_value(object_dict(hit).get(METADATA_PATH))


def metadata_hit_paths(metadata: object) -> list[str]:
    paths: list[str] = []
    for hit in object_list(object_dict(metadata).get("hits")):
        display_path = quality_metadata_path(_metadata_hit_path(hit))
        if display_path and display_path not in paths:
            paths.append(display_path)
    return paths


def first_metadata_hit_path(metadata: object) -> str | None:
    paths = metadata_hit_paths(metadata)
    return paths[0] if paths else None


def effective_metadata_path(metadata: object) -> str | None:
    meta = object_dict(metadata)
    display_path = quality_metadata_path(string_value(meta.get(METADATA_PATH)))
    if display_path:
        return display_path
    return first_metadata_hit_path(meta)
