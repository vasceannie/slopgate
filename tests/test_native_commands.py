from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies
from tests.native.launchers import write_python_launcher

import slopgate.installer.native.commands
from slopgate.installer.native.commands import (
    NATIVE_COMMAND_TIMEOUT_SECONDS,
    NativeCommandError,
    native_executable_available,
    run_native_command,
)

FAILURE_STATUS = 7
FAST_TIMEOUT_SECONDS = 2.0
BLOCK_SECONDS = 30
PROPERTY_EXAMPLES = 16
ARGUMENT_TEXT = strategies.text(
    alphabet=strategies.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        whitelist_characters=" ;'$&()",
    ),
    min_size=1,
    max_size=24,
)


def _write_manager(directory: Path, body: str) -> Path:
    return write_python_launcher(directory, "native-manager", body)


def _activate_manager(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    current = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + current)


def _property_argv_observation(
    tmp_path_factory: pytest.TempPathFactory, argument: str
) -> tuple[int, dict[str, object], str]:
    root = tmp_path_factory.mktemp("native-command")
    script = (
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "print(json.dumps({'argv': sys.argv[1:], 'cwd': str(Path.cwd())}))\n"
    )
    script_path = root / "argv-manager.py"
    script_path.write_text(script, encoding="utf-8")
    result = run_native_command(
        [sys.executable, str(script_path), argument],
        cwd=root,
        platform="test-host",
    )
    return result.returncode, json.loads(result.stdout), str(root)


def test_run_native_command_returns_nonzero_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manager(
        tmp_path,
        "import sys\nprint('manager output')\nprint('manager error', file=sys.stderr)\nsys.exit(7)\n",
    )
    _activate_manager(monkeypatch, tmp_path)

    result = run_native_command(["native-manager"], cwd=tmp_path, platform="test-host")

    assert result.returncode == FAILURE_STATUS, (
        "nonzero manager status should be returned, not raised"
    )
    assert result.stdout.strip() == "manager output", (
        "stdout should be captured for diagnostics"
    )
    assert result.stderr.strip() == "manager error", (
        "stderr should be captured for diagnostics"
    )


def test_run_native_command_reports_missing_executable(tmp_path: Path) -> None:
    with pytest.raises(NativeCommandError, match="not found on PATH"):
        run_native_command(
            ["slopgate-test-command-that-does-not-exist"],
            cwd=tmp_path,
            platform="test-host",
        )


def test_run_native_command_translates_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer.native.commands,
        "NATIVE_COMMAND_TIMEOUT_SECONDS",
        FAST_TIMEOUT_SECONDS,
    )

    with pytest.raises(NativeCommandError, match="command timed out") as error:
        run_native_command(
            [
                sys.executable,
                "-c",
                "import sys, threading; print('stdout marker', flush=True); "
                "print('stderr marker', file=sys.stderr, flush=True); "
                f"threading.Event().wait({BLOCK_SECONDS})",
            ],
            cwd=tmp_path,
            platform="test-host",
        )

    assert "stdout: stdout marker" in str(error.value), (
        "timeout diagnostics should retain flushed stdout"
    )
    assert "stderr: stderr marker" in str(error.value), (
        "timeout diagnostics should retain flushed stderr"
    )


def test_timeout_failure_decodes_non_utf8_byte_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = subprocess.TimeoutExpired(
        [sys.executable],
        FAST_TIMEOUT_SECONDS,
        output=b"\xffstdout",
        stderr=b"\xfe stderr",
    )

    def raise_timeout(
        argv: list[str], **options: object
    ) -> subprocess.CompletedProcess[str]:
        _ = argv, options
        raise failure

    monkeypatch.setattr(
        slopgate.installer.native.commands.subprocess, "run", raise_timeout
    )
    with pytest.raises(NativeCommandError) as error:
        run_native_command([sys.executable], cwd=tmp_path, platform="test-host")

    assert "stdout: �stdout" in str(error.value), (
        "timeout stdout should decode invalid UTF-8 with replacement"
    )
    assert "stderr: � stderr" in str(error.value), (
        "timeout stderr should decode invalid UTF-8 with replacement"
    )


def test_run_native_command_merges_environment_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manager(
        tmp_path,
        "import os\nprint(os.environ.get('SLOPGATE_CHILD_FLAG', 'missing'))\nprint(bool(os.environ.get('PATH')))\n",
    )
    _activate_manager(monkeypatch, tmp_path)

    result = run_native_command(
        ["native-manager"],
        cwd=tmp_path,
        platform="test-host",
        env={"SLOPGATE_CHILD_FLAG": "available"},
    )

    assert result.stdout.splitlines() == ["available", "True"], (
        "environment overrides should retain inherited PATH"
    )


def test_run_native_command_forces_no_color_and_removes_force_color(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manager(
        tmp_path,
        "import os\nprint(os.environ.get('NO_COLOR'))\nprint(os.environ.get('FORCE_COLOR', 'absent'))\n",
    )
    _activate_manager(monkeypatch, tmp_path)
    monkeypatch.setenv("FORCE_COLOR", "1")

    result = run_native_command(["native-manager"], cwd=tmp_path, platform="test-host")

    assert result.stdout.splitlines() == ["1", "absent"], (
        "native manager output must be color-free even when the parent requests color"
    )


def test_native_executable_available_resolves_and_rejects_names() -> None:
    assert native_executable_available(sys.executable), (
        "the active Python executable should resolve through shutil.which"
    )
    assert not native_executable_available("slopgate-no-such-manager-9931"), (
        "an absent executable should not be reported as available"
    )
    assert NATIVE_COMMAND_TIMEOUT_SECONDS > FAST_TIMEOUT_SECONDS, (
        "native commands should use the documented production timeout by default"
    )


@settings(max_examples=PROPERTY_EXAMPLES, deadline=None)
@given(argument=ARGUMENT_TEXT)
def test_run_native_command_property_preserves_argv_boundaries(
    tmp_path_factory: pytest.TempPathFactory, argument: str
) -> None:
    returncode, output, cwd = _property_argv_observation(tmp_path_factory, argument)

    assert (returncode, output) == (
        0,
        {"argv": [argument], "cwd": cwd},
    ), (
        "native commands should preserve arbitrary argument boundaries without shell parsing"
    )
