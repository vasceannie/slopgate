from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.installer import _opencode
import slopgate.installer._shared
from slopgate.resources import resource_path
from slopgate.util import platform

OPENCODE_PLUGIN_RESOURCE = "opencode_plugin.ts"


def test_opencode_renderer_embeds_install_identity_snapshot() -> None:
    template = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    identity = {
        "status": "compatible",
        "opencode_version": "1.18.19",
        "plugin_declared_version": "1.18.19",
        "plugin_lock_version": "1.18.19",
        "plugin_installed_version": "1.18.19",
        "slopgate_version": "2.1.6",
        "slopgate_binary": "/tmp/slopgate",
        "captured_at": "2026-08-22T00:00:00+00:00",
        "provenance": "install",
        "remediation": "none",
    }

    rendered = _opencode.render_opencode_plugin(template, "/tmp/slopgate", identity)

    assert '"__SLOPGATE_OPENCODE_IDENTITY__"' not in rendered, "placeholder leaked"
    assert '"opencode_version":"1.18.19"' in rendered, "runtime version not embedded"
    assert '"slopgate_binary":"/tmp/slopgate"' in rendered, "binary path not embedded"


def test_opencode_plugin_treats_empty_success_as_allow_noop() -> None:
    plugin = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
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
    template = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    rendered = _opencode.render_opencode_plugin(template, binary)
    assert (
        f"Bun.env.SLOPGATE_BIN ? [Bun.env.SLOPGATE_BIN] : {json.dumps([binary])}"
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


def _plant_opencode_user_leaf_symlink(tmp_path: Path) -> tuple[Path, Path]:
    outside = tmp_path / "outside" / "secret.ts"
    outside.parent.mkdir()
    outside.write_text("KEEP\n", encoding="utf-8")
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)
    return target, outside


def test_opencode_user_install_refuses_leaf_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    target, outside = _plant_opencode_user_leaf_symlink(tmp_path)
    assert _opencode.install_opencode(dry_run=False) == 1, (
        "user install must refuse a leaf symlink"
    )
    assert outside.read_text(encoding="utf-8") == "KEEP\n", (
        "external symlink targets must remain unchanged"
    )
    assert target.is_symlink(), "the planted leaf symlink must not be replaced"


def test_opencode_uninstall_removes_legacy_owned_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(platform, "is_windows", lambda: False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    target = tmp_path / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir(parents=True)
    target.write_text(
        "/* OpenCode Slopgate Plugin */\nconst SLOPGATE_BIN = \"slopgate\";\n",
        encoding="utf-8",
    )

    assert _opencode.uninstall_opencode(dry_run=False) == 0, (
        "legacy owned plugins must remain uninstallable"
    )
    assert not target.exists(), "legacy owned plugin should be removed"


def test_official_opencode_types_match_declared_target() -> None:
    matrix = json.loads(
        (Path(__file__).with_name("fixtures") / "opencode_hook_contract_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    plugin = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    target = matrix["compatibility_target"]["version"]

    assert target == _opencode.OPENCODE_TYPES_TARGET, (
        "installer types target must match the published OpenCode compatibility version"
    )
    assert f"@opencode-ai/plugin@{target}" in plugin, (
        "generated plugin types must name the official OpenCode package target"
    )
    assert "project?: unknown" in plugin, "official PluginInput.project is missing"
    assert "experimental_workspace?: unknown" in plugin, (
        "official PluginInput.experimental_workspace is missing"
    )
    assert "serverUrl?: URL" in plugin, "official PluginInput.serverUrl is missing"
    assert "options?: Record<string, unknown>" in plugin, (
        "official Plugin options argument is missing"
    )
    assert "output: string" in plugin, "official after-hook output must be a string"


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
    plugin = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    assert 'result.action === "warn" || result.action === "context"' in plugin
    assert "const message = result.reason || result.context" in plugin
    assert 'level: "warn"' in plugin


def test_opencode_plugin_forwards_documented_runtime_events() -> None:
    plugin = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    expected_fragments = [
        'event.type === "file.edited"',
        '"slopgate-file-edited"',
        'payloadForEvent("file.edited", "Write"',
        'event.type === "permission.replied"',
        'event.type === "session.compacted"',
        'event.type === "session.error"',
        'event.type === "session.status"',
        'event.type === "shell.env"',
        'event.type === "command.executed"',
        "eventToolArgs(event)",
        "payloadForEvent(",
        "logAdvisoryResult(",
    ]
    missing_fragments = [
        fragment for fragment in expected_fragments if fragment not in plugin
    ]
    assert missing_fragments == [], (
        "OpenCode plugin must forward documented runtime events"
    )


def test_opencode_plugin_preserves_session_created_identity_for_traces() -> None:
    plugin = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    expected_fragments = [
        "function eventIdentityFields(",
        'const data = objectValue(event, "data")',
        'const dataInfo = data ? objectValue(data, "info") : null',
        "const directSessionIdKeys = [",
        "const infoSessionIdKeys = [",
        '"sessionID"',
        '"callID"',
        '"id"',
        '"threadTitle"',
        '"conversationTitle"',
        'session_title_source: "opencode-event"',
        'session_identity_source: "opencode-event"',
        'payloadForEvent("session.created", "", {}, eventIdentityFields(event, true))',
    ]
    missing_fragments = [
        fragment for fragment in expected_fragments if fragment not in plugin
    ]
    assert missing_fragments == [], (
        "OpenCode plugin should preserve session-created identity metadata for traces"
    )


def test_opencode_plugin_uses_native_tool_fields_without_correlation_cache() -> None:
    plugin = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    forbidden_fragments = (
        "SESSION_ID",
        "postToolArgCache",
        "rememberToolArgs",
        "takeRememberedToolArgs",
        "POST_TOOL_ARG_CACHE_TTL_MS",
        "output.result",
        "input.cwd",
        "event.cwd",
    )
    required_fragments = (
        "input.sessionID",
        "input.callID",
        "output.args",
        "input.args",
        "output.title",
        "output.output",
        "output.metadata",
        'objectValue(event, "properties")',
    )
    assert not any(fragment in plugin for fragment in forbidden_fragments)
    assert all(fragment in plugin for fragment in required_fragments)


def test_opencode_plugin_records_conservative_tool_outcome_axes() -> None:
    plugin = resource_path(OPENCODE_PLUGIN_RESOURCE).read_text(encoding="utf-8")
    required_fragments = (
        "interface OpenCodeToolBeforeInput",
        "interface OpenCodeToolBeforeOutput",
        "interface OpenCodeToolAfterInput",
        "interface OpenCodeToolAfterOutput",
        "const preToolArgs = cloneArgs(outputArgs)",
        "const postToolArgs = cloneArgs(input.args)",
        '...outcomeFields("unknown", "unresolved", "unknown", "unresolved")',
        '...outcomeFields("returned", "pinned-source", "unknown", "unresolved")',
        '...outcomeFields("unknown", "unresolved", "partial", "local-observed")',
        "execution_outcome",
        "mutation_outcome",
        "evidence_tier",
        "tool_title: output.title",
        "tool_metadata: output.metadata",
        "tool_output: output.output",
        "unknown OpenCode tool effect; denying by default.",
        "isKnownEffectTool(",
    )
    assert all(fragment in plugin for fragment in required_fragments), (
        "OpenCode outcomes must use typed fields and conservative evidence tiers"
    )
    assert 'mutation_outcome: "committed"' not in plugin, (
        "OpenCode after hooks must not claim that a mutation was committed"
    )
