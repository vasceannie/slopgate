"""Shared JSON coercion helpers."""
from collections.abc import Mapping

JSONDict = dict[str, object]


def coerce_object_dict(value: object) -> JSONDict | None:
    if not isinstance(value, Mapping):
        return None
    result: JSONDict = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def coerce_bool_dict(value: object) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, bool] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, bool):
            result[key] = item
    return result


def coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
