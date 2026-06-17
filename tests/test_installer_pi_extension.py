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
    extension_path = tmp_path / ".pi" / "agent" / "extensions" / "slopgate.ts"
    content = extension_path.read_text(encoding="utf-8")
    assert "Pi Slopgate Extension" in content
    assert json.dumps(["/tmp/slopgate"]) in content
    assert '"handle", "--platform", "pi"' in content


def test_pi_project_scope_writes_repo_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    monkeypatch.chdir(tmp_path)
    assert slopgate.installer._pi.install_pi(dry_run=False, scope="project") == 0
    extension_path = tmp_path / ".pi" / "extensions" / "slopgate.ts"
    content = extension_path.read_text(encoding="utf-8")
    assert all(marker in content for marker in slopgate.installer._pi.PI_OWNERSHIP_MARKERS)


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
    extension_path = tmp_path / ".pi" / "agent" / "extensions" / "slopgate.ts"
    extension_path.parent.mkdir(parents=True)
    extension_path.write_text("export default function custom() {}\n", encoding="utf-8")
    assert slopgate.installer._pi.uninstall_pi(dry_run=False) == 1
    assert extension_path.read_text(encoding="utf-8") == "export default function custom() {}\n"
