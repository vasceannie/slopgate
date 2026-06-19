from __future__ import annotations

import json
from pathlib import Path

import pytest

import slopgate.installer
import slopgate.installer._pi
import slopgate.installer._shared


def _install_user_pi_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    assert slopgate.installer._pi.install_pi(dry_run=False, scope="user") == 0, (
        "install_pi should create a user-scoped Pi extension for uninstall tests"
    )
    return tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"


def _artifact_state(paths: dict[str, Path]) -> dict[str, bool]:
    return {name: path.exists() for name, path in paths.items()}


def _text_artifact_state(paths: dict[str, Path]) -> dict[str, str]:
    return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}


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
    package_path = extension_path.parent / "package.json"
    content = extension_path.read_text(encoding="utf-8")
    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert {
        "has_marker": "Pi Slopgate Extension" in content,
        "has_binary": json.dumps(["/tmp/slopgate"]) in content,
        "has_handle_args": '"handle", "--platform", "pi"' in content,
        "config_name": json.loads(config_path.read_text(encoding="utf-8"))["name"],
        "pi_tui_version": package["dependencies"]["@earendil-works/pi-tui"],
        "node_types_version": package["dependencies"]["@types/node"],
    } == {
        "has_marker": True,
        "has_binary": True,
        "has_handle_args": True,
        "config_name": "pi-slopgate",
        "pi_tui_version": "^0.79.6",
        "node_types_version": "^22.16.5",
    }, "Pi user install should write extension, config, and package metadata"


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
    assert all(
        marker in content for marker in slopgate.installer._pi.PI_OWNERSHIP_MARKERS
    )
    assert (extension_path.parent / "config.json").exists()
    assert (extension_path.parent / "package.json").exists()


def test_pi_user_extension_path_uses_global_agent_extension_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    expected = tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    assert slopgate.installer._pi.pi_user_extension_path() == expected, (
        "pi_user_extension_path should point at Pi's user agent extension directory"
    )


def test_pi_project_extension_path_uses_project_extension_dir(tmp_path: Path) -> None:
    expected = tmp_path / ".pi" / "extensions" / "pi-slopgate" / "index.ts"
    assert slopgate.installer._pi.pi_project_extension_path(tmp_path) == expected, (
        "pi_project_extension_path should point at the repo-local Pi extension"
    )


def test_pi_extension_has_owned_slopgate_recognizes_installed_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        slopgate.installer._shared, "find_binary", lambda: "/tmp/slopgate"
    )
    assert slopgate.installer._pi.install_pi(
        dry_run=False, scope="project", project_root=tmp_path
    ) == 0, "install_pi should create the project extension for ownership probing"
    extension_path = slopgate.installer._pi.pi_project_extension_path(tmp_path)
    assert slopgate.installer._pi.pi_extension_has_owned_slopgate(extension_path), (
        "pi_extension_has_owned_slopgate should recognize Slopgate's own template"
    )


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
    assert (
        legacy_path.read_text(encoding="utf-8")
        == "export default function custom() {}\n"
    )
    assert (
        tmp_path / ".pi" / "agent" / "extensions" / "pi-slopgate" / "index.ts"
    ).exists()


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
    assert (
        extension_path.read_text(encoding="utf-8")
        == "export default function custom() {}\n"
    )


def test_pi_uninstall_removes_canonical_config_and_owned_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension_path = _install_user_pi_extension(tmp_path, monkeypatch)
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

    config_path = extension_path.parent / "config.json"
    package_path = extension_path.parent / "package.json"
    paths = {
        "extension_exists": extension_path,
        "config_exists": config_path,
        "package_exists": package_path,
        "legacy_exists": legacy_path,
    }
    status = slopgate.installer._pi.uninstall_pi(dry_run=False, scope="user")

    assert {
        "status": status,
        **_artifact_state(paths),
    } == {
        "status": 0,
        "extension_exists": False,
        "config_exists": False,
        "package_exists": False,
        "legacy_exists": False,
    }, "Pi uninstall should remove canonical files and owned legacy extension"


def test_pi_uninstall_removes_owned_legacy_package_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension_path = _install_user_pi_extension(tmp_path, monkeypatch)
    legacy_package_path = extension_path.with_name("index.js")
    paths = {
        "extension_exists": extension_path,
        "config_exists": extension_path.parent / "config.json",
        "legacy_package_exists": legacy_package_path,
    }
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

    status = slopgate.installer._pi.uninstall_pi(dry_run=False, scope="user")

    assert {
        "status": status,
        **_artifact_state(paths),
    } == {
        "status": 0,
        "extension_exists": False,
        "config_exists": False,
        "legacy_package_exists": False,
    }, "Pi uninstall should remove the owned legacy package entry"


def test_pi_uninstall_preserves_unrecognized_artifact_but_removes_owned_leftovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension_path = _install_user_pi_extension(tmp_path, monkeypatch)
    config_path = extension_path.parent / "config.json"
    legacy_path = tmp_path / ".pi" / "agent" / "extensions" / "slopgate.ts"
    paths = {
        "extension_exists": extension_path,
        "legacy_exists": legacy_path,
    }
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

    status = slopgate.installer._pi.uninstall_pi(dry_run=False, scope="user")

    assert {
        "status": status,
        **_artifact_state(paths),
        **_text_artifact_state({"config_content": config_path}),
    } == {
        "status": 1,
        "extension_exists": False,
        "config_content": '{"name": "custom"}\n',
        "legacy_exists": False,
    }, "Pi uninstall should preserve custom config but remove owned leftovers"
