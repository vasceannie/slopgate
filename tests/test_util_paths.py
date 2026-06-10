from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.util import logger
from slopgate.util.payloads import is_bash_tool, is_shell_tool, shell_kind_for_tool
from slopgate.util.path_filters import is_third_party_or_virtualenv_path
from slopgate.util import platform
from slopgate.util.platform import (
    looks_like_windows_absolute_path,
    lower_path_for_match,
    normalize_path_for_match,
    resolve_path_for_match,
    user_config_dir,
    user_data_dir,
)


def _path_helper_results(cwd: Path) -> dict[str, object]:
    return {
        "third_party_site_packages": is_third_party_or_virtualenv_path(
            "pkg/.venv/lib/python/site-packages/mod.py"
        ),
        "authored_environment_package": is_third_party_or_virtualenv_path(
            "src/environment/package.py"
        ),
        "normalized": normalize_path_for_match(r"tests\unit\test_x.py "),
        "lowered": lower_path_for_match(r"SRC\Package\Mod.py"),
        "windows_drive": looks_like_windows_absolute_path(r"C:\\Users\\Trav\\x.py"),
        "windows_unc": looks_like_windows_absolute_path("\\\\server\\share\\x.py"),
        "resolved": resolve_path_for_match("src/pkg.py", cwd),
    }


def _xdg_helper_results(
    monkeypatch: pytest.MonkeyPatch,
    config_root: Path,
    data_root: Path,
) -> dict[str, Path | bool]:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return {
        "is_windows_bool": platform.is_windows(),
        "config": user_config_dir("slopgate-test"),
        "data": user_data_dir("slopgate-test"),
        "data_root_exists": data_root.exists(),
    }


def test_path_matching_helpers_normalize_platform_paths(tmp_path: Path) -> None:
    results = _path_helper_results(tmp_path)
    expected_resolved = resolve_path_for_match("src/pkg.py", tmp_path)

    assert results == {
        "third_party_site_packages": True,
        "authored_environment_package": False,
        "normalized": "tests/unit/test_x.py",
        "lowered": "src/package/mod.py",
        "windows_drive": True,
        "windows_unc": True,
        "resolved": expected_resolved,
    }


def test_user_platform_dirs_respect_xdg_config_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "xdg-config"
    data_root = tmp_path / "xdg-data"
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    results = _xdg_helper_results(monkeypatch, config_root, data_root)

    assert results == {
        "is_windows_bool": False,
        "config": config_root / "slopgate-test",
        "data": Path.home() / ".local" / "share" / "slopgate-test",
        "data_root_exists": False,
    }


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [
        ("Bash", "bash"),
        ("power-shell", "powershell"),
        ("cmd.exe", "cmd"),
        ("local-shell", "unknown"),
        ("Read", None),
    ],
)
def test_shell_tool_kind_normalizes_known_shell_aliases(
    tool_name: str,
    expected: str | None,
) -> None:
    result = shell_kind_for_tool(tool_name)

    assert result == expected
    assert is_shell_tool(tool_name) is (expected is not None)
    assert is_bash_tool(tool_name) is (expected == "bash")


def test_logger_helpers_emit_json_levels(capsys: pytest.CaptureFixture[str]) -> None:
    logger.debug("debug event", path="src/debug.py")
    logger.info("info event", path="src/info.py")
    logger.warning("warning event", path="src/warning.py")
    logger.error("error event", path="src/error.py")

    payloads = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    expected_events = [
        {"level": "debug", "message": "debug event", "path": "src/debug.py"},
        {"level": "info", "message": "info event", "path": "src/info.py"},
        {"level": "warning", "message": "warning event", "path": "src/warning.py"},
        {"level": "error", "message": "error event", "path": "src/error.py"},
    ]

    assert [
        {key: payload[key] for key in expected_events[index]}
        for index, payload in enumerate(payloads)
    ] == expected_events
    assert all("timestamp" in payload for payload in payloads)
