from __future__ import annotations
import json
from pathlib import Path
import pytest
import slopgate.installer
import slopgate.installer._shared
from slopgate.constants import PLATFORM_CLAUDE
from slopgate.installer._shared import (
    UnsafeInstallPathError,
    backup_existing_file,
    backup_existing_file_and_report,
    base_invocation,
    coerce_hook_entries,
    contained_scope_root,
    find_binary,
    merge_owned_hooks_into,
    require_contained_install_path,
    require_json_object,
    write_contained_json,
    write_contained_text,
    write_json_with_backup,
)


def hook_commands(settings_path: Path) -> list[str]:
    hooks = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]
    return [
        hook["command"]
        for entry in hooks["PreToolUse"]
        for hook in entry.get("hooks", [])
    ]


@pytest.mark.parametrize(
    "command", ["slopgate handle", "slopgate.exe handle", "python -m slopgate handle"]
)
def test_command_ownership_recognizes_exact_slopgate_invocations(command: str) -> None:
    assert slopgate.installer._shared.command_is_slopgate_hook(command)


def test_command_ownership_recognizes_windows_powershell_hook_command() -> None:
    command = slopgate.installer._shared.hook_command(
        "C:\\\\Tools\\\\Slopgate Bin\\\\slopgate.exe", "handle", windows=True
    )
    assert slopgate.installer._shared.command_is_slopgate_hook(command)


@pytest.mark.parametrize(
    "command",
    ["my-slopgate-helper handle", "/opt/not-slopgate handle", "slopgate-doc handle"],
)
def test_command_ownership_preserves_unrelated_slopgate_named_helpers(
    command: str,
) -> None:
    assert not slopgate.installer._shared.command_is_slopgate_hook(command)


def _old_powershell_hook() -> str:
    return slopgate.installer._shared.hook_command(
        "C:\\\\Old Tools\\\\slopgate.exe", "handle", windows=True
    )


def _seed_claude_hook_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_command: str,
    second_command: str,
) -> Path:
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {"type": "command", "command": first_command},
                                {"type": "command", "command": second_command},
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return settings_path


def test_claude_reinstall_replaces_powershell_owned_hook_and_preserves_user_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_owned = _old_powershell_hook()
    settings_path = _seed_claude_hook_settings(
        tmp_path, monkeypatch, "my-slopgate-helper handle", old_owned
    )
    monkeypatch.setattr(slopgate.installer._shared, "find_binary", lambda: "slopgate")
    result = slopgate.installer.install_claude(dry_run=False)
    assert {"result": result, "commands": hook_commands(settings_path)} == {
        "result": 0,
        "commands": [
            "my-slopgate-helper handle",
            slopgate.installer._shared.hook_command(
                "slopgate", "handle", "--platform", PLATFORM_CLAUDE
            ),
        ],
    }


def test_claude_uninstall_removes_powershell_owned_hook_and_preserves_user_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = _seed_claude_hook_settings(
        tmp_path, monkeypatch, "slopgate-doc handle", _old_powershell_hook()
    )
    result = slopgate.installer.uninstall_claude(dry_run=False)
    assert {"result": result, "commands": hook_commands(settings_path)} == {
        "result": 0,
        "commands": ["slopgate-doc handle"],
    }


def test_find_binary_returns_string() -> None:
    result = find_binary()
    assert isinstance(result, str)
    assert result != ""


def test_base_invocation_returns_module_args_for_python_executable() -> None:
    import sys

    result = base_invocation(sys.executable)
    assert result == [sys.executable, "-m", "slopgate"]


def test_base_invocation_returns_direct_invocation_for_named_binary() -> None:
    result = base_invocation("slopgate")
    assert result == ["slopgate"]


def test_coerce_hook_entries_filters_non_dicts() -> None:
    raw: list[object] = [{"type": "command", "command": "x"}, "not-a-dict", None, 42]
    result = coerce_hook_entries(raw)
    assert result == [{"type": "command", "command": "x"}]


def test_coerce_hook_entries_returns_empty_for_non_list() -> None:
    assert coerce_hook_entries("not-a-list") == []


def test_require_json_object_parses_valid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "settings.json"
    config_file.write_text('{"hooks": {}}', encoding="utf-8")
    result = require_json_object(config_file, "settings", action="install")
    assert result == {"hooks": {}}


def test_require_json_object_returns_none_for_invalid_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_file = tmp_path / "bad.json"
    config_file.write_text("not json", encoding="utf-8")
    result = require_json_object(config_file, "settings", action="install")
    assert result is None


def test_merge_owned_hooks_into_replaces_hooks_key(tmp_path: Path) -> None:
    config: dict[str, object] = {"other": "value", "hooks": {}}
    managed: dict[str, list[dict[str, object]]] = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "slopgate handle"}],
            }
        ]
    }
    merge_owned_hooks_into(config, managed)
    hooks = config.get("hooks")
    assert isinstance(hooks, dict)
    assert "PreToolUse" in hooks


def test_backup_existing_file_creates_sibling_backup(tmp_path: Path) -> None:
    original = tmp_path / "settings.json"
    original.write_text('{"key": "value"}', encoding="utf-8")
    backup_path = backup_existing_file(original)
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == '{"key": "value"}'


def test_backup_existing_file_returns_none_when_file_absent(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    result = backup_existing_file(missing)
    assert result is None


def test_backup_existing_file_and_report_prints_backup_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = tmp_path / "settings.json"
    original.write_text("{}", encoding="utf-8")
    backup_existing_file_and_report(original, "settings")
    output = capsys.readouterr().out
    assert "Backed up" in output


def test_write_json_with_backup_writes_formatted_json(tmp_path: Path) -> None:
    target = tmp_path / "output.json"
    payload: dict[str, object] = {"hooks": {}, "version": 1}
    write_json_with_backup(target, payload, "output")
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == payload


def test_require_contained_install_path_accepts_real_nested_file(tmp_path: Path) -> None:
    target = tmp_path / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir()
    resolved = require_contained_install_path(target, tmp_path)
    assert resolved == target.resolve(), (
        "contained real paths should resolve under the selected root"
    )


def test_require_contained_install_path_allows_symlink_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root)
    target = linked_root / "plugins" / "slopgate-plugin.ts"
    resolved = require_contained_install_path(target, linked_root)
    assert resolved == real_root / "plugins" / "slopgate-plugin.ts", (
        "a symlink install root is trusted; only hops after that root are checked"
    )


@pytest.mark.parametrize(
    ("plant", "expected_fragment"),
    [
        pytest.param("leaf", "symlink", id="leaf-file"),
        pytest.param("parent", "symlink", id="parent-dir"),
        pytest.param("outside", "outside the selected install root", id="escaped-path"),
    ],
)
def test_require_contained_install_path_rejects_unsafe_targets(
    tmp_path: Path, plant: str, expected_fragment: str
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside" / "secret.ts"
    outside.parent.mkdir()
    outside.write_text("KEEP\n", encoding="utf-8")
    if plant == "leaf":
        target = root / "plugins" / "slopgate-plugin.ts"
        target.parent.mkdir()
        target.symlink_to(outside)
    elif plant == "parent":
        (root / "plugins").symlink_to(outside.parent)
        target = root / "plugins" / "slopgate-plugin.ts"
    else:
        target = outside
    with pytest.raises(UnsafeInstallPathError, match=expected_fragment):
        require_contained_install_path(target, root)
    assert outside.read_text(encoding="utf-8") == "KEEP\n", (
        "rejected paths must leave the external target unchanged"
    )


def test_write_contained_text_replaces_real_file_and_keeps_backup(
    tmp_path: Path,
) -> None:
    target = tmp_path / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir()
    target.write_text("custom plugin\n", encoding="utf-8")
    written = write_contained_text(target, "owned plugin\n", root=tmp_path, label="file")
    assert written.read_text(encoding="utf-8") == "owned plugin\n", (
        "safe writes should replace the real file in place"
    )
    backups = sorted(target.parent.glob("slopgate-plugin.ts.slopgate-bak-*"))
    assert len(backups) == 1, "existing real files should be backed up before replace"
    assert backups[0].read_text(encoding="utf-8") == "custom plugin\n"


def test_write_contained_text_rejects_leaf_symlink_and_preserves_external(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside" / "secret.ts"
    outside.parent.mkdir()
    outside.write_text("KEEP\n", encoding="utf-8")
    target = tmp_path / "plugins" / "slopgate-plugin.ts"
    target.parent.mkdir()
    target.symlink_to(outside)
    with pytest.raises(UnsafeInstallPathError, match="symlink"):
        write_contained_text(target, "owned plugin\n", root=tmp_path, label="file")
    assert outside.read_text(encoding="utf-8") == "KEEP\n", (
        "leaf symlink writes must not overwrite the external target"
    )
    assert target.is_symlink(), "the planted leaf symlink must remain a symlink"


def test_contained_scope_root_selects_project_or_user(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    user_root = tmp_path / "home" / ".claude"
    project_target = project_root / ".claude" / "settings.json"
    user_target = user_root / "settings.json"
    assert (
        contained_scope_root(
            project_target, project_root=project_root, user_root=user_root
        )
        == project_root
    ), "paths under the project root must use the project root"
    assert (
        contained_scope_root(
            user_target, project_root=project_root, user_root=user_root
        )
        == user_root
    ), "paths outside the project root must use the user root"


def test_write_contained_json_writes_formatted_object(tmp_path: Path) -> None:
    target = tmp_path / "hooks" / "hooks.json"
    payload: dict[str, object] = {"hooks": {}, "version": 1}
    written = write_contained_json(target, payload, root=tmp_path, label="hooks")
    assert json.loads(written.read_text(encoding="utf-8")) == payload, (
        "contained JSON writes should match write_json_with_backup formatting"
    )
