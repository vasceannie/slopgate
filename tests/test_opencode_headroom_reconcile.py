from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import opencode_headroom_reconcile


def _entry(proxy_url: object, **options: object) -> list[object]:
    return [
        opencode_headroom_reconcile.PLUGIN_PATH,
        {"proxyUrl": proxy_url, **options},
    ]


def _write_config(path: Path, plugin_entries: list[object]) -> bytes:
    path.write_text(json.dumps({"plugin": plugin_entries}, indent=2) + "\n")
    return path.read_bytes()


def _assert_malformed_entry_is_rejected(
    config: Path,
    backup_root: Path,
) -> tuple[bytes, bool]:
    with pytest.raises(opencode_headroom_reconcile.ReconcileError):
        opencode_headroom_reconcile.reconcile(config, backup_root)

    return config.read_bytes(), backup_root.exists()


def test_existing_json_override_preserves_unknown_options_byte_for_byte(
    tmp_path: Path,
) -> None:
    config = tmp_path / "opencode.json"
    original = _write_config(
        config,
        [_entry("http://127.0.0.1:8788", cache=True, nested={"mode": "local"})],
    )
    backup_root = tmp_path / "backups"

    status, backup = opencode_headroom_reconcile.reconcile(config, backup_root)

    assert status == "preserved-local-override", "local overrides must be preserved"
    assert backup is None, "preserved overrides must not create a backup"
    assert config.read_bytes() == original, (
        "preserved overrides must keep original bytes"
    )
    assert not backup_root.exists(), "preserved overrides need no backup directory"


def test_existing_jsonc_override_is_preserved_byte_for_byte(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    config.write_text(
        f'''{{
  // This comment and trailing comma must survive.
  "plugin": [
    [
      "{opencode_headroom_reconcile.PLUGIN_PATH}",
      {{
        "proxyUrl": "http://localhost:8788",
        "futureOption": {{"enabled": true}},
      }},
    ],
  ],
}}
'''
    )
    original = config.read_bytes()
    backup_root = tmp_path / "backups"

    status, backup = opencode_headroom_reconcile.reconcile(config, backup_root)

    assert status == "preserved-local-override", "JSONC overrides must be preserved"
    assert backup is None, "preserved JSONC overrides must not create a backup"
    assert config.read_bytes() == original, (
        "JSONC preservation must keep original bytes"
    )
    assert not backup_root.exists(), (
        "preserved JSONC overrides need no backup directory"
    )


@pytest.mark.parametrize(
    "proxy_url",
    [
        "http://127.0.0.1:8788",
        "http://localhost:8788",
        "http://192.168.1.40:8788",
        "https://headroom.internal.example:8443/proxy",
        "http://[::1]:8788",
    ],
)
def test_local_and_network_http_urls_are_valid(proxy_url: str) -> None:
    assert opencode_headroom_reconcile.is_valid_proxy_url(proxy_url), (
        "local and network HTTP proxy URLs should be valid"
    )


def test_missing_entry_is_inserted_with_backup_and_verification(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    original = _write_config(config, ["file:///existing/plugin.js"])
    backup_root = tmp_path / "backups"

    status, backup = opencode_headroom_reconcile.reconcile(config, backup_root)

    assert status == "repaired", "missing plugin entries should be repaired"
    assert backup is not None, "repairing a config should create a backup"
    assert backup.read_bytes() == original, "the backup should contain original bytes"
    repaired_status, _, _ = opencode_headroom_reconcile.inspect_config(
        config.read_text()
    )
    assert repaired_status == "already-present", "repaired config must contain the plugin"


def test_empty_strict_json_plugin_array_remains_strict_json(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    config.write_text('{"plugin":[]}\n', encoding="utf-8")
    backup_root = tmp_path / "backups"

    status, backup = opencode_headroom_reconcile.reconcile(config, backup_root)
    document = json.loads(config.read_text(encoding="utf-8"))

    assert status == "repaired", "empty plugin arrays should be repaired"
    assert backup is not None, "repairing an empty plugin array should create a backup"
    assert document["plugin"][0] == opencode_headroom_reconcile.REQUIRED_ENTRY, (
        "strict JSON consumers must parse the inserted plugin entry"
    )


@pytest.mark.parametrize(
    ("config_body", "layout"),
    [
        pytest.param(
            '{\n  "plugin": [\n    "file:///existing/plugin.js",\n  ],\n}\n',
            "trailing-comma array",
            id="trailing-comma",
        ),
        pytest.param(
            '{\n  // keep me\n  "plugin": [\n    ["other", {"a": 1}],\n'
            "    /* block */\n  ],\n}\n",
            "jsonc comments and trailing comma",
            id="jsonc-comments",
        ),
    ],
)
def test_missing_entry_is_inserted_into_difficult_arrays(
    tmp_path: Path, config_body: str, layout: str
) -> None:
    config = tmp_path / "opencode.json"
    config.write_text(config_body)
    backup_root = tmp_path / "backups"

    status, backup = opencode_headroom_reconcile.reconcile(config, backup_root)

    assert status == "repaired", f"{layout} must remain repairable"
    assert backup is not None, "repairing a config should create a backup"
    repaired_status, _, _ = opencode_headroom_reconcile.inspect_config(
        config.read_text()
    )
    assert repaired_status == "already-present", (
        f"the repaired {layout} config must parse with valid separators"
    )


@pytest.mark.parametrize(
    "entry",
    [
        [opencode_headroom_reconcile.PLUGIN_PATH],
        [opencode_headroom_reconcile.PLUGIN_PATH, []],
        _entry(""),
        _entry("ftp://127.0.0.1:8788"),
        _entry("http://user:password@127.0.0.1:8788"),
        _entry("http://127.0.0.1:99999"),
    ],
)
def test_malformed_entries_fail_without_mutation(
    tmp_path: Path, entry: list[object]
) -> None:
    config = tmp_path / "opencode.json"
    original = _write_config(config, [entry])
    backup_root = tmp_path / "backups"

    config_bytes, backup_exists = _assert_malformed_entry_is_rejected(
        config, backup_root
    )

    assert config_bytes == original, "malformed entries must not change the config"
    assert not backup_exists, "malformed entries must not create a backup"


def test_duplicate_entries_fail_without_mutation(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    original = _write_config(
        config,
        [
            _entry(opencode_headroom_reconcile.PROXY_URL),
            _entry("http://127.0.0.1:8788"),
        ],
    )
    backup_root = tmp_path / "backups"

    with pytest.raises(
        opencode_headroom_reconcile.ReconcileError,
        match="duplicate",
    ):
        opencode_headroom_reconcile.reconcile(config, backup_root)

    assert config.read_bytes() == original, (
        "duplicate entries must not change the config"
    )
    assert not backup_root.exists(), "duplicate entries must not create a backup"


def test_ambiguous_path_reference_fails_without_mutation(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    original = _write_config(
        config,
        [
            [
                "file:///other.js",
                {"unexpected": opencode_headroom_reconcile.PLUGIN_PATH},
            ]
        ],
    )
    backup_root = tmp_path / "backups"

    with pytest.raises(
        opencode_headroom_reconcile.ReconcileError,
        match="ambiguous",
    ):
        opencode_headroom_reconcile.reconcile(config, backup_root)

    assert config.read_bytes() == original, (
        "ambiguous references must not change the config"
    )
    assert not backup_root.exists(), "ambiguous references must not create a backup"


def test_duplicate_json_keys_fail_without_mutation(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    config.write_text(
        '{"plugin": [], "plugin": [["duplicate", {"proxyUrl": "http://x"}]]}\n'
    )
    original = config.read_bytes()
    backup_root = tmp_path / "backups"

    with pytest.raises(
        opencode_headroom_reconcile.ReconcileError,
        match="duplicate JSON object key",
    ):
        opencode_headroom_reconcile.reconcile(config, backup_root)

    assert config.read_bytes() == original, (
        "duplicate JSON keys must not change the config"
    )
    assert not backup_root.exists(), "duplicate JSON keys must not create a backup"


def test_cli_reports_preserved_local_override(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    original = _write_config(config, [_entry("http://127.0.0.1:8788")])
    backup_root = tmp_path / "backups"

    # Exercise the real script with explicit fixture paths.
    script = Path(__file__).parents[1] / "scripts" / "opencode_headroom_reconcile.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--config",
            str(config),
            "--backup-root",
            str(backup_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "status=preserved-local-override" in result.stdout, (
        "the CLI must report the preserved local override"
    )
    assert result.stderr == "", "successful reconciliation must not write stderr"
    assert config.read_bytes() == original, (
        "the CLI must preserve original config bytes"
    )
    assert not backup_root.exists(), "preserved overrides must not create CLI backups"


def test_symlink_config_is_refused_without_detaching_target(tmp_path: Path) -> None:
    target = tmp_path / "managed-opencode.json"
    original = _write_config(target, [])
    config = tmp_path / "opencode.json"
    config.symlink_to(target)
    backup_root = tmp_path / "backups"

    with pytest.raises(opencode_headroom_reconcile.ReconcileError, match="symlink"):
        opencode_headroom_reconcile.reconcile(config, backup_root)

    assert config.is_symlink(), "refused reconciliation must preserve the managed symlink"
    assert target.read_bytes() == original, "refused reconciliation must preserve target bytes"
    assert not backup_root.exists(), "refused symlink configs must not create backups"


def test_invalid_utf8_config_is_refused_without_traceback_state(tmp_path: Path) -> None:
    config = tmp_path / "opencode.json"
    original = b'{"plugin":["\xff"]}\n'
    config.write_bytes(original)
    backup_root = tmp_path / "backups"

    with pytest.raises(opencode_headroom_reconcile.ReconcileError, match="cannot read config"):
        opencode_headroom_reconcile.reconcile(config, backup_root)

    assert config.read_bytes() == original, "invalid UTF-8 must remain byte-for-byte unchanged"
    assert not backup_root.exists(), "invalid UTF-8 must not create backups"
