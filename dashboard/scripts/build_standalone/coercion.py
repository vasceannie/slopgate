from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias, cast

JSONDict: TypeAlias = dict[str, object]


def coerce_object_dict(value: object) -> JSONDict | None:
    if not isinstance(value, Mapping):
        return None
    result: JSONDict = {}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str):
            result[key] = item
    return result


def coerce_dict_list(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    result: list[JSONDict] = []
    for item in cast(list[object], value):
        record = coerce_object_dict(item)
        if record is not None:
            result.append(record)
    return result


def coerce_object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def coerce_bool_dict(value: object) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, bool] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str) and isinstance(item, bool):
            result[key] = item
    return result


def coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            result.append(item)
    return result
