from __future__ import annotations

import threading
from pathlib import Path

from hypothesis import given, strategies
import pytest

from slopgate.constants import LINT_SCOPE_ALL, LINT_SCOPE_CHANGED, LINT_SCOPE_STAGED
from slopgate.lint._config import (
    get_config,
    get_quality_scope,
    load_config,
    reset_quality_scope,
    set_config,
    set_quality_scope,
)

THREAD_WAIT_SECONDS = 1.0
VALID_SCOPE_VALUES = (LINT_SCOPE_ALL, LINT_SCOPE_CHANGED, LINT_SCOPE_STAGED, None)
INVALID_SCOPE_VALUES = ("", "workspace", "ALL")


def _repo_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    return root


def _capture_thread_config(
    root: Path,
    ready: threading.Event,
    release: threading.Event,
    results: dict[str, Path],
    key: str,
) -> None:
    cfg = load_config(root)
    set_config(cfg)
    ready.set()
    _ = release.wait(THREAD_WAIT_SECONDS)
    results[key] = get_config().project_root


def _capture_isolated_roots(
    first_root: Path, second_root: Path
) -> tuple[bool, bool, dict[str, Path]]:
    first_ready = threading.Event()
    second_ready = threading.Event()
    release = threading.Event()
    results: dict[str, Path] = {}
    first = threading.Thread(
        target=_capture_thread_config,
        args=(first_root, first_ready, release, results, "first"),
    )
    second = threading.Thread(
        target=_capture_thread_config,
        args=(second_root, second_ready, release, results, "second"),
    )

    first.start()
    second.start()
    first_observed = first_ready.wait(THREAD_WAIT_SECONDS)
    second_observed = second_ready.wait(THREAD_WAIT_SECONDS)
    release.set()
    first.join()
    second.join()
    return first_observed, second_observed, results


def test_lint_config_is_isolated_per_thread(tmp_path: Path) -> None:
    first_root = _repo_root(tmp_path, "repo-a")
    second_root = _repo_root(tmp_path, "repo-b")
    first_observed, second_observed, results = _capture_isolated_roots(
        first_root, second_root
    )

    assert first_observed, "First thread should load its lint config"
    assert second_observed, "Second thread should load its lint config"
    assert results["first"] == first_root.resolve(), (
        "First thread should retain its own lint project root"
    )
    assert results["second"] == second_root.resolve(), (
        "Second thread should retain its own lint project root"
    )


@given(strategies.sampled_from(VALID_SCOPE_VALUES))
def test_quality_scope_round_trips_valid_scope_property(scope: str | None) -> None:
    token = set_quality_scope(scope)

    assert get_quality_scope() == scope, "Valid quality scope should round-trip"
    reset_quality_scope(token)


@given(strategies.sampled_from(INVALID_SCOPE_VALUES))
def test_quality_scope_rejects_invalid_scope_property(scope: str) -> None:
    with pytest.raises(ValueError, match="unsupported lint quality scope"):
        set_quality_scope(scope)
