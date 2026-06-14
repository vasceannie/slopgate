"""Support helpers for JS/TS changed-test CLI behavior tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from hypothesis import strategies

from slopgate.cli import js_ts_tests
from slopgate.lint._config import reset_config

JS_TS_STEM_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=16
)
JS_TS_SUFFIX = strategies.sampled_from((".js", ".jsx", ".ts", ".tsx"))


def prepare_js_ts_project(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    package = root / "apps" / "web"
    source = package / "src" / "components"
    source.mkdir(parents=True)
    (package / "package.json").write_text(
        '{"scripts":{"test":"vitest run"}}\n', encoding="utf-8"
    )
    (source / "Button.tsx").write_text(
        "export const Button = () => null\n", encoding="utf-8"
    )
    (source / "Button.test.tsx").write_text(
        "test('button', () => {})\n", encoding="utf-8"
    )
    (source / "Card.ts").write_text("export const card = 1\n", encoding="utf-8")
    (source / "Card.spec.ts").write_text("test('card', () => {})\n", encoding="utf-8")
    monkeypatch.chdir(root)
    reset_config()


def run_js_ts_executor_property_case(
    stem: str, suffix: str
) -> tuple[int, tuple[str, ...]]:
    observed_command: list[str] = []
    with TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        package_root = root / "packages" / "widget"
        source_root = package_root / "src"
        source_root.mkdir(parents=True)
        (package_root / "package.json").write_text(
            '{"scripts":{"test":"vitest run"}}\n', encoding="utf-8"
        )
        test_path = f"packages/widget/src/{stem}.test{suffix}"
        (root / test_path).write_text("test('value', () => {})\n", encoding="utf-8")

        def record_npm_test(
            command: list[str], *, cwd: Path, check: bool
        ) -> subprocess.CompletedProcess[str]:
            assert cwd == package_root, "npm should run at the owning package root"
            assert check is False, "npm execution should return exit codes"
            observed_command.extend(command)
            return subprocess.CompletedProcess(command, 0)

        with patch.object(js_ts_tests.subprocess, "run", side_effect=record_npm_test):
            result = js_ts_tests.execute_default_js_ts_tests((test_path,), root=root)
    return result, tuple(observed_command)
