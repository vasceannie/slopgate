from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, strategies

from slopgate.enrichment.quality_enrichers._magic_number_import_hints import (
    append_importable_constant_hints,
    constant_file_candidates,
    extract_importable_constants,
    module_name_for_import,
)

IDENTIFIER = strategies.from_regex("[A-Z][A-Z0-9_]{0,10}", fullmatch=True)
LOWER_IDENTIFIER = strategies.from_regex("[a-z][a-z0-9_]{0,10}", fullmatch=True)
CONSTANT_VALUES = strategies.one_of(
    strategies.integers(min_value=0, max_value=10),
    strategies.floats(
        min_value=0.0,
        max_value=10.0,
        allow_nan=False,
        allow_infinity=False,
        width=32,
    ),
    strategies.text(alphabet="abcxyz", min_size=1, max_size=8),
)


def _constant_source(name: str, value: int | float | str) -> str:
    return f"{name} = {value!r}\n"


@given(name=IDENTIFIER, value=CONSTANT_VALUES)
def test_extract_importable_constants_keeps_uppercase_literals_property(
    name: str,
    value: int | float | str,
) -> None:
    with TemporaryDirectory() as raw_path:
        constants_file = Path(raw_path) / "constants.py"
        constants_file.write_text(_constant_source(name, value), encoding="utf-8")

        constants = extract_importable_constants(constants_file)

    assert [(constant.name, constant.value) for constant in constants] == [
        (name, value)
    ]


@given(module_name=LOWER_IDENTIFIER)
def test_constant_file_candidates_are_existing_constant_modules_property(
    module_name: str,
) -> None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        constants_file = root / f"{module_name}_constants.py"
        constants_file.write_text("VALUE = 1\n", encoding="utf-8")

        candidates = constant_file_candidates(constants_file, root)

    assert candidates == [constants_file.resolve()]


@given(module_name=LOWER_IDENTIFIER)
def test_module_name_for_import_drops_source_root_property(module_name: str) -> None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        constants_file = root / "src" / "package" / f"{module_name}.py"

        module = module_name_for_import(constants_file, root)

    assert module == f"package.{module_name}"


@given(name=IDENTIFIER, value=CONSTANT_VALUES)
def test_append_importable_constant_hints_mentions_exact_import_property(
    name: str,
    value: int | float | str,
) -> None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        constants_file = root / "constants.py"
        constants_file.write_text(_constant_source(name, value), encoding="utf-8")
        extras: list[str] = []

        appended = append_importable_constant_hints(
            extras, constants_file, root, {value}
        )

    assert {
        "appended": appended,
        "heading": extras[0],
        "import": any(f"from constants import {name}" in item for item in extras),
    } == {"appended": True, "heading": "Exact constant match:", "import": True}
