"""Tests for shared finding metadata path helpers."""

from __future__ import annotations

import pytest
from hypothesis import given, strategies

from slopgate.constants import METADATA_PATH
from slopgate.util.metadata_paths import (
    effective_metadata_path,
    first_metadata_hit_path,
    metadata_hit_paths,
    quality_metadata_path,
)


def _expected_quality_hit_paths(hits: list[str]) -> list[str]:
    paths: list[str] = []
    for hit in hits:
        display_path = quality_metadata_path(hit)
        if display_path and display_path not in paths:
            paths.append(display_path)
    return paths


@pytest.mark.parametrize(
    ("path_value", "expected"),
    [
        pytest.param(None, None, id="missing_path"),
        pytest.param("content", None, id="content_sentinel"),
        pytest.param("patch.diff", None, id="patch_sentinel"),
        pytest.param("src/app.py", "src/app.py", id="source_path"),
    ],
)
def test_quality_metadata_path_filters_only_non_final_paths(
    path_value: str | None, expected: str | None
) -> None:
    result = quality_metadata_path(path_value)

    assert result == expected, f"{path_value!r} should normalize to {expected!r}"


@given(strategies.text(max_size=200))
def test_quality_metadata_path_returns_original_or_none(raw_path: str) -> None:
    result = quality_metadata_path(raw_path)

    assert result is None or result == raw_path, (
        "quality_metadata_path should only reject paths, never rewrite them"
    )


def test_metadata_hit_paths_keeps_unique_quality_hits() -> None:
    metadata = {
        "hits": [
            "src/app.py",
            {METADATA_PATH: "tests/test_app.py"},
            "src/app.py",
            {METADATA_PATH: "content"},
            {METADATA_PATH: "patch.diff"},
        ]
    }

    result = metadata_hit_paths(metadata)

    assert result == ["src/app.py", "tests/test_app.py"], (
        "metadata_hit_paths should de-duplicate hits and ignore sentinel paths"
    )


@given(strategies.lists(strategies.text(max_size=80), max_size=20))
def test_metadata_hit_paths_preserves_unique_quality_string_hits(
    raw_hits: list[str],
) -> None:
    result = metadata_hit_paths({"hits": raw_hits})

    assert result == _expected_quality_hit_paths(raw_hits), (
        "metadata_hit_paths should keep first-seen quality paths only"
    )


def test_first_metadata_hit_path_returns_first_quality_hit() -> None:
    metadata = {"hits": ["content", {METADATA_PATH: "src/app.py"}]}

    result = first_metadata_hit_path(metadata)

    assert result == "src/app.py", "first_metadata_hit_path should skip sentinels"


def test_effective_metadata_path_prefers_canonical_path_over_hits() -> None:
    metadata = {METADATA_PATH: "src/direct.py", "hits": ["src/hit.py"]}

    result = effective_metadata_path(metadata)

    assert result == "src/direct.py", "canonical metadata path should win over hits"


def test_effective_metadata_path_falls_back_to_first_quality_hit() -> None:
    metadata = {METADATA_PATH: "content", "hits": ["src/fallback.py"]}

    result = effective_metadata_path(metadata)

    assert result == "src/fallback.py", (
        "first quality hit should replace path sentinels"
    )
