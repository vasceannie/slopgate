from __future__ import annotations
import pytest
import json
from pathlib import Path
from slopgate.installer import _opencode
import slopgate.installer._shared
from slopgate.resources import resource_path
from slopgate.util import platform


def _opencode_plugin_source() -> str:
    return resource_path("opencode_plugin.ts").read_text(encoding="utf-8")


def test_opencode_plugin_treats_empty_success_as_allow_noop() -> None:
    plugin = _opencode_plugin_source()
    assert "empty enforcer response" not in plugin
    assert "if (!trimmed) return null" in plugin
    assert "exits 0 with no stdout" in plugin


def test_opencode_installer_uses_appdata_plugin_dir_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setattr(platform, "is_windows", lambda: True)
    monkeypatch.setenv("APPDATA", str(appdata))
    assert (
        _opencode.opencode_user_plugin_path()
        == appdata / "opencode" / "plugins" / "slopgate-plugin.ts"
    )


def test_opencode_installer_embeds_safely_quoted_binary_fallback() -> None:
    binary = 'C:\\Users\\Trav App\\bin\\slopgate "quoted".exe'
    template = _opencode_plugin_source()
    rendered = _opencode.render_opencode_plugin(template, binary)
    assert (
        f'Bun.env.SLOPGATE_BIN ? [Bun.env.SLOPGATE_BIN] : {json.dumps([binary])}'
        in rendered
    )
    assert '"__SLOPGATE_BIN__"' not in rendered


def test_opencode_install_backs_up_existing_plugin_before_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/Slopgate Bin/slopgate"
    )
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text("custom plugin\n", encoding="utf-8")
    assert _opencode.install_opencode(dry_run=False) == 0
    backups = sorted(target.parent.glob("slopgate-plugin.ts.slopgate-bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "custom plugin\n"
    installed = target.read_text(encoding="utf-8")
    assert (
        'Bun.env.SLOPGATE_BIN ? [Bun.env.SLOPGATE_BIN] : ["/tmp/Slopgate Bin/slopgate"]'
        in installed
    )


def test_opencode_uninstall_refuses_unrecognized_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text("custom plugin\n", encoding="utf-8")
    assert _opencode.uninstall_opencode(dry_run=False) == 1
    assert target.read_text(encoding="utf-8") == "custom plugin\n"


def test_opencode_uninstall_refuses_custom_plugin_with_incidental_marker_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text(
        "// docs mention slopgate handle --platform opencode, but this is custom\n",
        encoding="utf-8",
    )
    assert _opencode.uninstall_opencode(dry_run=False) == 1
    assert target.exists()
    assert "this is custom" in target.read_text(encoding="utf-8")


def test_opencode_plugin_logs_posttool_context_actions() -> None:
    plugin = _opencode_plugin_source()
    assert 'result.action === "warn" || result.action === "context"' in plugin
    assert "const message = result.reason || result.context" in plugin
    assert 'level: "warn"' in plugin


def _assert_posttool_arg_cache_contract(plugin: str) -> None:
    expected_cache_contract = [
        "const postToolArgCache: ToolArgsCacheEntry[] = []",
        "function rememberToolArgs(",
        "function takeRememberedToolArgs(",
        "tool_input: preToolArgs",
        "rememberToolArgs(input.tool, currentDirectory, preToolArgs)",
        "const rememberedArgs = takeRememberedToolArgs(input.tool, currentDirectory)",
        "const postToolArgs = { ...rememberedArgs, ...cloneArgs(output.args) }",
        "tool_input: postToolArgs",
    ]
    missing_contract = [line for line in expected_cache_contract if line not in plugin]
    assert missing_contract == [], (
        "OpenCode plugin lost pretool/posttool arg cache contract"
    )


def _assert_posttool_arg_cache_policy(plugin: str) -> None:
    expected_policy = [
        "POST_TOOL_ARG_CACHE_TTL_MS = 5 * 60 * 1000",
        "POST_TOOL_ARG_CACHE_MAX_ENTRIES = 50",
        "entry.tool === toolName && entry.cwd === cwd",
        "postToolArgCache.splice(index, 1)",
    ]
    missing_policy = [line for line in expected_policy if line not in plugin]
    assert missing_policy == [], (
        "OpenCode plugin cache should stay TTL-bounded, scoped, and consumed"
    )


def test_opencode_plugin_caches_pretool_args_for_posttool_backstops() -> None:
    plugin = _opencode_plugin_source()
    assert "tool_input: preToolArgs" in plugin
    _assert_posttool_arg_cache_contract(plugin)


def test_opencode_plugin_cache_is_bounded_ttl_scoped_and_consumed() -> None:
    plugin = _opencode_plugin_source()
    assert "POST_TOOL_ARG_CACHE_TTL_MS" in plugin
    _assert_posttool_arg_cache_policy(plugin)
