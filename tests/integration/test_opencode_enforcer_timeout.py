from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from slopgate._types import object_dict
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path
from tests.integration.opencode_plugin_v2_support import (
    link_v2_dependencies,
    v2_before_input,
    v2_plugin_setup_source,
)


pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")


def _run_hanging_enforcer(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    pid_path = tmp_path / "child.pid"
    executable = tmp_path / "slopgate"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path
if sys.argv[1:3] == ["repair", "status"]:
    print(json.dumps({"status": "clean"}))
else:
    Path(os.environ["CHILD_PID_PATH"]).write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(30)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "2.2.5"},
        ),
        encoding="utf-8",
    )
    runner = tmp_path / "runner.ts"
    runner.write_text(
        v2_plugin_setup_source(plugin_path, tmp_path)
        + v2_before_input("write", "session", {"path": "sample.py", "content": "x"}),
        encoding="utf-8",
    )
    link_v2_dependencies(tmp_path)
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "SLOPGATE_ENFORCER_TIMEOUT_MS": "100",
            "CHILD_PID_PATH": str(pid_path),
        },
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )


def test_hanging_enforcer_returns_and_kills_child(tmp_path: Path) -> None:
    result = _run_hanging_enforcer(tmp_path)

    assert result.returncode != 0, "managed timeout must fail closed"
    assert "timed out" in result.stderr
    pid = int((tmp_path / "child.pid").read_text(encoding="utf-8"))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError("timed-out enforcer child is still alive")


def _run_enforcer_case(
    tmp_path: Path,
    script: str,
    *,
    managed: bool,
    tool_name: str,
) -> subprocess.CompletedProcess[str]:
    if managed:
        (tmp_path / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n", encoding="utf-8"
        )
    executable = tmp_path / "slopgate"
    executable.write_text(script, encoding="utf-8")
    executable.chmod(0o755)
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "2.2.5"},
        ),
        encoding="utf-8",
    )
    runner = tmp_path / "runner.ts"
    runner.write_text(
        v2_plugin_setup_source(plugin_path, tmp_path)
        + f"""
try {{
{v2_before_input(tool_name, "session", {"path": "sample.py", "content": "x"})}
  console.log("allowed")
}} catch (error) {{
  const detail = error && typeof error === "object"
    ? {{ _tag: error._tag, message: error.message }}
    : {{ _tag: "Error", message: String(error) }}
  process.stderr.write(JSON.stringify(detail) + "\\n")
  process.exitCode = 1
}}
""",
        encoding="utf-8",
    )
    link_v2_dependencies(tmp_path)
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "SLOPGATE_DAEMON_SOCKET": str(tmp_path / "missing.sock"),
            "SLOPGATE_ENFORCER_TIMEOUT_MS": "100",
        },
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )


def test_enforcer_malformed_json_fails_closed_in_managed_repo(tmp_path: Path) -> None:
    result = _run_enforcer_case(
        tmp_path,
        '#!/usr/bin/env python3\nimport json\nimport sys\nif sys.argv[1:3] == ["repair", "status"]:\n    print(json.dumps({"status": "clean"}))\nelse:\n    print(\'not-json\')\n',
        managed=True,
        tool_name="write",
    )

    assert result.returncode != 0
    error = object_dict(json.loads(result.stderr))
    assert error["_tag"] == "Tool.Error"
    assert "slopgate degraded mode: enforcer call failed in managed repo." in str(
        error["message"]
    )


def test_enforcer_spawn_failure_is_not_blocking_outside_managed_repo(
    tmp_path: Path,
) -> None:
    result = _run_enforcer_case(
        tmp_path,
        "#!/usr/bin/env/does-not-exist\n",
        managed=False,
        tool_name="write",
    )

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout


def test_enforcer_timeout_allows_read_only_tool_in_managed_repo(tmp_path: Path) -> None:
    result = _run_enforcer_case(
        tmp_path,
        '#!/usr/bin/env python3\nimport json\nimport sys\nimport time\nif sys.argv[1:3] == ["repair", "status"]:\n    print(json.dumps({"status": "clean"}))\nelse:\n    time.sleep(30)\n',
        managed=True,
        tool_name="read",
    )

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout
