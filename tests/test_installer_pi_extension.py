from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import slopgate.installer
import slopgate.installer._pi
import slopgate.installer._shared


def test_pi_install_writes_global_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    assert slopgate.installer.install_platform("pi", dry_run=False) == 0
    extension_path = (
        tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    )
    config_path = extension_path.parent / "config.json"
    content = extension_path.read_text(encoding="utf-8")
    assert "Pi Slopgate Extension" in content
    assert json.dumps(["/tmp/slopgate"]) in content
    assert '"handle", "--platform", "pi"' in content
    assert json.loads(config_path.read_text(encoding="utf-8"))["name"] == "pi-slopgate"


def test_pi_project_scope_writes_repo_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    assert slopgate.installer._pi.install_pi(dry_run=False, scope="project") == 0
    extension_path = tmp_path / ".pi" / "extensions" / "pi-slopgate" / "index.ts"
    content = extension_path.read_text(encoding="utf-8")
    assert all(marker in content for marker in slopgate.installer._pi.PI_OWNERSHIP_MARKERS)
    assert (extension_path.parent / "config.json").exists()


def test_pi_install_removes_owned_legacy_standalone_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    legacy_path = tmp_path / ".pi" / "agent" / "extensions" / "slopgate.ts"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        "\n".join(
            (
                "/* Pi Slopgate Extension */",
                "const SLOPGATE_ARGV = []",
                "// slopgate handle --platform pi",
            )
        ),
        encoding="utf-8",
    )

    assert slopgate.installer._pi.install_pi(dry_run=False, scope="user") == 0
    assert not legacy_path.exists()
    assert list(legacy_path.parent.glob("slopgate.ts.slopgate-bak-*"))


def test_pi_install_refuses_to_silently_remove_unrecognized_legacy_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    legacy_path = tmp_path / ".pi" / "agent" / "extensions" / "slopgate.ts"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("export default function custom() {}\n", encoding="utf-8")

    assert slopgate.installer._pi.install_pi(dry_run=False, scope="user") == 1
    assert legacy_path.read_text(encoding="utf-8") == "export default function custom() {}\n"
    assert (
        tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    ).exists()


def test_pi_extension_falls_back_to_python_module_invocation() -> None:
    from slopgate.resources import resource_path

    template = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    extension = slopgate.installer._pi.render_pi_extension(template, sys.executable)
    assert "__SLOPGATE_BIN__" not in extension
    assert json.dumps([sys.executable, "-m", "slopgate"]) in extension
    assert f'{json.dumps(sys.executable)}, "handle"' not in extension


def test_pi_extension_uses_documented_input_handled_action() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert '{ action: "handled" }' in extension
    assert "{ handled: true }" not in extension


def test_pi_extension_uses_documented_input_event_text() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert "text?: string" in extension
    assert "function promptFromEvent(event: PiEventLike): string" in extension
    assert 'return event.text || event.prompt || ""' in extension
    assert "prompt: promptFromEvent(event)" in extension


def test_pi_extension_supports_documented_input_transform_result() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert 'action?: "continue" | "handled" | "transform"' in extension
    assert 'return { action: "handled" }' in extension
    assert 'action: "transform", text' in extension
    assert "inputTransformFromUpdatedInput(result?.updated_input)" in extension


def test_pi_extension_maps_tool_args_and_results_from_pi_events() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert "args?: Record<string, unknown>" in extension
    assert "result?: unknown" in extension
    assert "return event.input || event.args || {}" in extension
    assert "return event.content ?? event.result ?? event.message ?? null" in extension
    assert "tool_input: toolInputFromEvent(event)" in extension
    assert "tool_result: toolResultFromEvent(event)" in extension
    assert "tool_response: toolResultFromEvent(event)" in extension


def test_pi_extension_injects_session_context_through_before_agent_start() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert "systemPrompt?: string" in extension
    assert "function beforeAgentStartResult(" in extension
    assert "systemPrompt: `${systemPrompt}\\n\\n${result.context}`.trim()" in extension
    assert 'return beforeAgentStartResult(event, await enforce("before_agent_start", event, ctx))' in extension


def test_pi_extension_does_not_require_node_buffer_global() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert "Buffer" not in extension


def test_pi_extension_suppresses_node_builtin_type_noise_without_require() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert "@earendil-works/pi-coding-agent" not in extension
    assert 'from "node:child_process"' in extension
    assert 'from "node:fs"' in extension
    assert 'from "node:path"' in extension
    assert 'from "node:process"' in extension
    assert extension.count("@ts-ignore Pi provides Node built-ins at runtime") == 4
    assert "runtimeRequire" not in extension
    assert "require(" not in extension
    assert 'eval)("require")' not in extension
    assert "require is not defined" not in extension
    assert "interface PiExtensionAPI" in extension
    assert "event: PiEventLike, ctx: PiContextLike" in extension


def test_pi_extension_keeps_post_tool_findings_advisory() -> None:
    from slopgate.resources import resource_path

    extension = resource_path("pi_extension.ts").read_text(encoding="utf-8")
    assert 'pi.on("tool_result"' in extension
    assert 'pi.on("tool_execution_end"' in extension
    assert "throw new Error" not in extension


def test_pi_uninstall_refuses_unrecognized_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    extension_path = (
        tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    )
    extension_path.parent.mkdir(parents=True)
    extension_path.write_text("export default function custom() {}\n", encoding="utf-8")
    assert slopgate.installer._pi.uninstall_pi(dry_run=False) == 1
    assert extension_path.read_text(encoding="utf-8") == "export default function custom() {}\n"


def test_pi_uninstall_removes_canonical_config_and_owned_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    assert slopgate.installer._pi.install_pi(dry_run=False, scope="user") == 0
    legacy_path = tmp_path / ".pi" / "agent" / "extensions" / "slopgate.ts"
    legacy_path.write_text(
        "\n".join(
            (
                "/* Pi Slopgate Extension */",
                "const SLOPGATE_ARGV = []",
                "// slopgate handle --platform pi",
            )
        ),
        encoding="utf-8",
    )

    extension_path = (
        tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    )
    config_path = extension_path.parent / "config.json"
    assert slopgate.installer._pi.uninstall_pi(dry_run=False, scope="user") == 0
    assert not extension_path.exists()
    assert not config_path.exists()
    assert not legacy_path.exists()


def test_pi_uninstall_removes_owned_legacy_package_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    assert slopgate.installer._pi.install_pi(dry_run=False, scope="user") == 0
    extension_path = (
        tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    )
    legacy_package_path = extension_path.with_name("index.js")
    legacy_package_path.write_text(
        "\n".join(
            (
                "export default function piSlopgate() {}",
                "// pi-slopgate",
                "// slopgate handle --platform pi",
            )
        ),
        encoding="utf-8",
    )

    assert slopgate.installer._pi.uninstall_pi(dry_run=False, scope="user") == 0
    assert not extension_path.exists()
    assert not (extension_path.parent / "config.json").exists()
    assert not legacy_package_path.exists()


def test_pi_uninstall_preserves_unrecognized_artifact_but_removes_owned_leftovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    assert slopgate.installer._pi.install_pi(dry_run=False, scope="user") == 0
    extension_path = (
        tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    )
    config_path = extension_path.parent / "config.json"
    legacy_path = tmp_path / ".pi" / "agent" / "extensions" / "slopgate.ts"
    config_path.write_text('{"name": "custom"}\n', encoding="utf-8")
    legacy_path.write_text(
        "\n".join(
            (
                "/* Pi Slopgate Extension */",
                "const SLOPGATE_ARGV = []",
                "// slopgate handle --platform pi",
            )
        ),
        encoding="utf-8",
    )

    assert slopgate.installer._pi.uninstall_pi(dry_run=False, scope="user") == 1
    assert not extension_path.exists()
    assert config_path.read_text(encoding="utf-8") == '{"name": "custom"}\n'
    assert not legacy_path.exists()
