from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import pytest

from slopgate.cli.commands import cmd_handle

_OPENCODE_COMPAT_PAYLOAD = """{
  "session_id": "ses_opencode_compat",
  "cwd": "/tmp",
  "hook_event_name": "PreToolUse",
  "hook_source": "opencode-plugin",
  "tool_name": "Write",
  "tool_input": {"file_path": "/etc/passwd", "content": "blocked"}
}"""


def test_cmd_handle_uses_opencode_adapter_for_compat_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SLOPGATE_DAEMON_SOCKET", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(_OPENCODE_COMPAT_PAYLOAD))

    exit_code = cmd_handle(argparse.Namespace(platform="claude"))

    rendered = json.loads(capsys.readouterr().out)
    assert exit_code == 0, "OpenCode compatibility handling should succeed"
    assert rendered["action"] == "block", (
        "OpenCode-origin payloads should use the OpenCode adapter"
    )
