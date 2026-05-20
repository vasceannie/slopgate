from __future__ import annotations

from typing import cast

def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw_dict = cast(dict[object, object], value)
    return {str(key): item for key, item in raw_dict.items()}


def _string_value(value: object, default: str = "") -> str:
    return default if value is None else str(value)


def _bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return bool(value)


def _int_value(value: object, default: int) -> int:
    if value is None:
        return default
    return int(str(value))


def _float_value(value: object, default: float) -> float:
    if value is None:
        return default
    return float(str(value))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    raw_list = cast(list[object], value)
    return [str(item) for item in raw_list]


def _command_map(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}

    raw_dict = cast(dict[object, object], value)
    commands: dict[str, list[str]] = {}
    for key, item in raw_dict.items():
        if isinstance(item, list):
            raw_list = cast(list[object], item)
            commands[str(key)] = [str(entry) for entry in raw_list]
    return commands
