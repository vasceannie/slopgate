from __future__ import annotations

from hypothesis import given, strategies

from dashboard.scripts.build_standalone.coercion import (
    coerce_bool_dict,
    coerce_dict_list,
    coerce_object_dict,
    coerce_object_list,
    coerce_str_list,
)

MIXED_SCALARS = strategies.one_of(
    strategies.none(),
    strategies.booleans(),
    strategies.integers(),
    strategies.text(max_size=20),
)
MIXED_KEYS = strategies.one_of(strategies.integers(), strategies.text(max_size=20))
MIXED_DICTS = strategies.dictionaries(MIXED_KEYS, MIXED_SCALARS, max_size=6)


def test_coerce_object_dict_keeps_string_keys() -> None:
    assert coerce_object_dict({"event": "stop", 3: "ignored"}) == {"event": "stop"}


def test_coerce_object_dict_returns_none_for_non_mapping() -> None:
    assert coerce_object_dict(["event"]) is None


def test_coerce_dict_list_filters_non_mappings() -> None:
    assert coerce_dict_list([{"rule_id": "PY-CODE-013"}, "ignored"]) == [
        {"rule_id": "PY-CODE-013"}
    ]


def test_coerce_object_list_preserves_list_values() -> None:
    value = ["stdout", 2]

    assert coerce_object_list(value) == value


def test_coerce_object_list_returns_empty_for_non_list() -> None:
    assert coerce_object_list("stdout") == []


def test_coerce_bool_dict_filters_non_bool_values() -> None:
    assert coerce_bool_dict({"enabled": True, "name": "rule", 2: False}) == {
        "enabled": True
    }


def test_coerce_str_list_filters_non_strings() -> None:
    assert coerce_str_list(["events", 1, "rules", None, True]) == ["events", "rules"]


def test_coerce_str_list_returns_empty_for_non_list() -> None:
    assert coerce_str_list("events") == []


@given(value=MIXED_DICTS)
def test_coerce_object_dict_keeps_string_keys_property(
    value: dict[object, object],
) -> None:
    expected = {key: item for key, item in value.items() if isinstance(key, str)}

    assert coerce_object_dict(value) == expected


@given(
    value=strategies.lists(strategies.one_of(MIXED_DICTS, MIXED_SCALARS), max_size=8)
)
def test_coerce_dict_list_keeps_mapping_records_property(value: list[object]) -> None:
    expected = [
        coerced for item in value if (coerced := coerce_object_dict(item)) is not None
    ]

    assert coerce_dict_list(value) == expected


@given(value=strategies.lists(MIXED_SCALARS, max_size=8))
def test_coerce_object_list_preserves_lists_property(value: list[object]) -> None:
    assert coerce_object_list(value) == value


@given(value=MIXED_DICTS)
def test_coerce_bool_dict_keeps_string_bool_items_property(
    value: dict[object, object],
) -> None:
    expected = {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, bool)
    }

    assert coerce_bool_dict(value) == expected


@given(value=strategies.lists(MIXED_SCALARS, max_size=8))
def test_coerce_str_list_keeps_strings_property(value: list[object]) -> None:
    expected = [item for item in value if isinstance(item, str)]

    assert coerce_str_list(value) == expected
