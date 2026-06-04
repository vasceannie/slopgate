from __future__ import annotations

from pathlib import Path

from hypothesis import given, strategies
import pytest

from slopgate.quality import constant_index
from slopgate.quality.constant_index import (
    ConstantIndex,
    StringConstantMatch,
    build_project_constant_index,
    find_string_constant,
    get_session_constant_index,
    iter_constant_candidate_paths,
    set_session_constant_index,
    suggest_constant_name,
)


def test_iter_constant_candidate_paths_returns_sorted_known_files(tmp_path: Path) -> None:
    constants = tmp_path / "constants.py"
    constants.write_text('API_URL = "https://example.test"\n', encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "paths.py").write_text('CACHE_DIR = "/tmp/cache"\n', encoding="utf-8")

    assert iter_constant_candidate_paths(tmp_path) == [config_dir / "paths.py", constants]


def test_constant_index_discovers_string_constants_from_known_files(
    tmp_path: Path,
) -> None:
    constants = tmp_path / "constants.py"
    constants.write_text(
        'API_URL = "https://example.test"\nCOUNT = 3\n',
        encoding="utf-8",
    )

    index = build_project_constant_index(tmp_path, use_mtime_cache=False)

    match = index.find_string_constant("https://example.test")
    assert {
        "type": isinstance(index, ConstantIndex),
        "match": match,
        "first_file": index.first_constants_file(),
    } == {
        "type": True,
        "match": StringConstantMatch("API_URL", constants, 1),
        "first_file": constants,
    }


def test_session_constant_index_supplies_find_string_constant(tmp_path: Path) -> None:
    constants = tmp_path / "constants.py"
    constants.write_text('TOKEN = "secret-value"\n', encoding="utf-8")
    index = build_project_constant_index(tmp_path, use_mtime_cache=False)

    set_session_constant_index(index)

    assert {
        "session": get_session_constant_index(),
        "match": find_string_constant("secret-value"),
        "missing": find_string_constant("missing"),
    } == {
        "session": index,
        "match": StringConstantMatch("TOKEN", constants, 1),
        "missing": None,
    }


def test_find_string_constant_builds_session_index_from_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constants = tmp_path / "settings.py"
    constants.write_text('ENVIRONMENT = "local-dev"\n', encoding="utf-8")

    monkeypatch.setattr(constant_index, "_session_index", None)
    match = find_string_constant("local-dev", root=tmp_path)

    assert match == StringConstantMatch("ENVIRONMENT", constants, 1)


@given(strategies.text(max_size=80))
def test_suggest_constant_name_returns_valid_uppercase_identifier_property(
    value: str,
) -> None:
    suggestion = suggest_constant_name(value)

    assert {
        "upper": suggestion.upper(),
        "starts_with_letter": suggestion[0].isalpha(),
        "max_length": len(suggestion) <= 48,
        "characters": all(char.isalnum() or char == "_" for char in suggestion),
    } == {
        "upper": suggestion,
        "starts_with_letter": True,
        "max_length": True,
        "characters": True,
    }
