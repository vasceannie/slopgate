#!/usr/bin/env python3
"""ForceDash canvas server with slopgate config management API.

Replaces: python3 -m http.server 18834 --directory ~/.openclaw/canvas/forcedash
Adds:
  GET  /api/config   → reads ~/.config/slopgate/config.json from SSH_HOST
  POST /api/config   → writes it back (read-modify-write with delta patch)
  GET  /api/health   → { ok, ssh_host, ssh_ok }
  GET  /api/harness/status → read-only Claude/Codex/OpenCode hook install status
"""
from collections.abc import Mapping
import http.server
import json
import os
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from socketserver import BaseServer
from typing import TypeAlias, cast

JSONDict: TypeAlias = dict[str, object]

CANVAS_DIR = Path.home() / ".openclaw/canvas/forcedash"
SSH_HOST = os.environ.get("SLOPGATE_SSH_HOST", "little")
CONFIG_PATH = os.environ.get("SLOPGATE_CONFIG_PATH", "~/.config/slopgate/config.json")
TRACE_DIR = os.environ.get("SLOPGATE_TRACE_DIR", "~/.config/slopgate/logs")
PORT = int(os.environ.get("PORT", "18834"))
BIND = os.environ.get("BIND", "0.0.0.0")
SSE_HEARTBEAT_SECONDS = 15
SNAPSHOT_TIMEOUT_SECONDS = 90


def _coerce_object_dict(value: object) -> JSONDict | None:
    if not isinstance(value, Mapping):
        return None
    result: JSONDict = {}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str):
            result[key] = item
    return result


def _coerce_bool_dict(value: object) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, bool] = {}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str) and isinstance(item, bool):
            result[key] = item
    return result


def _coerce_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            result.append(item)
    return result


def _ssh_python(
    script: str,
    *,
    input_text: str | None = None,
    timeout: int = 8,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", SSH_HOST, f"python3 - <<'PY'\n{script}\nPY"],
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def ssh_read_config() -> tuple[JSONDict, str | None]:
    """Read config from remote. Returns (config_dict, error_str)."""
    try:
        r = _ssh_python(
            "from pathlib import Path\nprint((Path.home() / '.config' / 'slopgate' / 'config.json').read_text())"
        )
        if r.returncode != 0:
            return {}, f"SSH exited {r.returncode}: {r.stderr.strip()}"
        payload: object = json.loads(r.stdout)
        config = _coerce_object_dict(payload)
        if config is None:
            return {}, "Config payload must be a JSON object"
        return config, None
    except subprocess.TimeoutExpired:
        return {}, "SSH timeout"
    except json.JSONDecodeError as e:
        return {}, f"Config parse error: {e}"
    except Exception as e:
        return {}, str(e)


def ssh_harness_status() -> tuple[JSONDict, str | None]:
    """Read-only hook/harness status from remote. Returns (status_dict, error_str)."""
    script = r'''
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

home = Path.home()
expected = {
    "claude": [
        "SessionStart", "CwdChanged", "UserPromptSubmit", "PreToolUse",
        "PermissionRequest", "PostToolUse", "PostToolUseFailure", "Stop",
        "SubagentStop", "TaskCompleted", "TeammateIdle", "InstructionsLoaded",
        "ConfigChange",
    ],
    "codex": ["SessionStart", "PreToolUse", "PermissionRequest", "PostToolUse", "UserPromptSubmit", "Stop"],
}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"json_parse_error: {exc.msg}"
    except OSError as exc:
        return None, f"read_error: {type(exc).__name__}"


def commands_in(value):
    found = []
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str):
            found.append(command)
        for item in value.values():
            found.extend(commands_in(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(commands_in(item))
    return found


def summarize_hooks(hooks, expected_events):
    if not isinstance(hooks, dict):
        hooks = {}
    present = sorted(k for k in expected_events if k in hooks)
    missing = sorted(k for k in expected_events if k not in hooks)
    commands = commands_in(hooks)
    vf_commands = [cmd for cmd in commands if "slopgate" in cmd and "handle" in cmd]
    return {
        "configured_events": present,
        "missing_events": missing,
        "expected_events": expected_events,
        "hook_entry_count": sum(len(v) if isinstance(v, list) else 1 for v in hooks.values()),
        "slopgate_command_count": len(vf_commands),
        "all_commands_reference_slopgate": bool(commands) and len(vf_commands) == len(commands),
    }


def dry_run(platform):
    candidates = [home / ".local" / "bin" / "slopgate", shutil.which("slopgate")]
    binary = next((str(p) for p in candidates if p and Path(str(p)).exists()), None)
    if not binary:
        return {"available": False, "ok": False, "note": "slopgate binary not found"}
    try:
        proc = subprocess.run(
            [binary, "install", platform, "--dry-run"],
            cwd=str(home),
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        return {"available": True, "ok": proc.returncode == 0, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"available": True, "ok": False, "note": "dry-run timeout"}
    except Exception as exc:
        return {"available": True, "ok": False, "note": type(exc).__name__}


def status_from(installed, partial=False, error=None):
    if error and error != "missing":
        return "error"
    if installed:
        return "installed"
    if partial:
        return "partial"
    return "missing"

# Claude Code
claude_path = home / ".claude" / "settings.json"
claude_data, claude_err = read_json(claude_path)
claude_hooks = summarize_hooks(claude_data.get("hooks") if isinstance(claude_data, dict) else {}, expected["claude"])
claude_installed = claude_err is None and not claude_hooks["missing_events"] and claude_hooks["slopgate_command_count"] > 0
claude_partial = claude_err is None and (bool(claude_hooks["configured_events"]) or claude_hooks["slopgate_command_count"] > 0)

# Codex
codex_hooks_path = home / ".codex" / "hooks.json"
codex_data, codex_err = read_json(codex_hooks_path)
codex_hooks = summarize_hooks(codex_data.get("hooks") if isinstance(codex_data, dict) else {}, expected["codex"])
codex_toml = home / ".codex" / "config.toml"
try:
    codex_toml_text = codex_toml.read_text(encoding="utf-8")
    codex_feature = bool(re.search(r"(?m)^\s*codex_hooks\s*=\s*true\b", codex_toml_text))
    codex_feature_error = None
except FileNotFoundError:
    codex_feature = False
    codex_feature_error = "missing"
except OSError as exc:
    codex_feature = False
    codex_feature_error = type(exc).__name__
codex_installed = codex_err is None and codex_feature and not codex_hooks["missing_events"] and codex_hooks["slopgate_command_count"] > 0
codex_partial = codex_err is None and (bool(codex_hooks["configured_events"]) or codex_hooks["slopgate_command_count"] > 0 or codex_feature)

# OpenCode
opencode_plugin = home / ".config" / "opencode" / "plugins" / "slopgate-plugin.ts"
opencode_disabled = home / ".config" / "opencode" / "plugins.disabled" / "slopgate-plugin.ts"
try:
    plugin_text = opencode_plugin.read_text(encoding="utf-8")[:12000]
    plugin_present = True
    plugin_error = None
except FileNotFoundError:
    plugin_text = ""
    plugin_present = False
    plugin_error = "missing"
except OSError as exc:
    plugin_text = ""
    plugin_present = False
    plugin_error = type(exc).__name__
opencode_marker = "slopgate" in plugin_text and "handle" in plugin_text
opencode_disabled_present = opencode_disabled.exists()

platforms = [
    {
        "id": "claude",
        "label": "Claude Code",
        "capability": "full",
        "support": "richest hook support / production",
        "status": status_from(claude_installed, claude_partial, claude_err),
        "config_path": "~/.claude/settings.json",
        "config_exists": claude_err is None,
        "error": None if claude_err in (None, "missing") else claude_err,
        "dry_run": dry_run("claude"),
        **claude_hooks,
    },
    {
        "id": "codex",
        "label": "Codex",
        "capability": "partial",
        "support": "partial hooks; requires codex_hooks feature flag",
        "status": status_from(codex_installed, codex_partial, codex_err or codex_feature_error),
        "config_path": "~/.codex/hooks.json",
        "config_exists": codex_err is None,
        "feature_flag_path": "~/.codex/config.toml",
        "feature_flag_enabled": codex_feature,
        "error": None if (codex_err in (None, "missing") and codex_feature_error in (None, "missing")) else (codex_err or codex_feature_error),
        "dry_run": dry_run("codex"),
        **codex_hooks,
    },
    {
        "id": "opencode",
        "label": "OpenCode",
        "capability": "degraded",
        "support": "plugin-mediated; prompt/stop controls are advisory/degraded",
        "status": "installed" if plugin_present and opencode_marker else ("disabled" if opencode_disabled_present and not plugin_present else status_from(False, plugin_present, plugin_error)),
        "config_path": "~/.config/opencode/plugins/slopgate-plugin.ts",
        "config_exists": plugin_present,
        "plugin_contains_slopgate": opencode_marker,
        "disabled_plugin_present": opencode_disabled_present,
        "error": None if plugin_error in (None, "missing") else plugin_error,
        "dry_run": dry_run("opencode"),
        "configured_events": ["tool.execute.before", "tool.execute.after", "session.created", "session.idle", "permission.asked"] if plugin_present and opencode_marker else [],
        "missing_events": [],
        "expected_events": ["tool.execute.before", "tool.execute.after", "session.created", "session.idle", "permission.asked"],
        "hook_entry_count": 1 if plugin_present else 0,
        "slopgate_command_count": 1 if opencode_marker else 0,
        "all_commands_reference_slopgate": bool(opencode_marker),
    },
]

print(json.dumps({"ok": True, "checked_at": datetime.now(timezone.utc).isoformat(), "platforms": platforms}))
'''
    try:
        r = _ssh_python(script)
        if r.returncode != 0:
            return {}, f"SSH exited {r.returncode}: {r.stderr.strip()}"
        payload: object = json.loads(r.stdout)
        status = _coerce_object_dict(payload)
        if status is None:
            return {}, "Harness status payload must be a JSON object"
        return status, None
    except subprocess.TimeoutExpired:
        return {}, "SSH timeout"
    except json.JSONDecodeError as e:
        return {}, f"Harness status parse error: {e}"
    except Exception as e:
        return {}, str(e)


def ssh_write_config(config: JSONDict) -> str | None:
    """Write config to remote. Returns error_str or None on success."""
    try:
        payload = json.dumps(config, indent=2)
        r = _ssh_python(
            "import sys\nfrom pathlib import Path\nPath.home().joinpath('.config', 'slopgate', 'config.json').write_text(sys.stdin.read())",
            input_text=payload,
        )
        if r.returncode != 0:
            return f"SSH write exited {r.returncode}: {r.stderr.strip()}"
        return None
    except subprocess.TimeoutExpired:
        return "SSH timeout"
    except Exception as e:
        return str(e)


def _snapshot_lookback_hours(path: str) -> int:
    parsed = urlparse(path)
    params = parse_qs(parsed.query)
    raw = (params.get("lookback_hours") or params.get("hours") or ["168"])[0]
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        hours = 168
    return max(1, min(hours, 720))


def ssh_trace_snapshot(lookback_hours: int) -> tuple[JSONDict, str | None]:
    """Read a bounded, current trace snapshot from the live log host."""
    script = f"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypeAlias, cast
import json

JSONDict: TypeAlias = dict[str, object]
LOOKBACK_HOURS = {lookback_hours}
LOG_DIR = Path.home() / ".config" / "slopgate" / "logs"
JSONL_FILES = ["events.jsonl", "rules.jsonl", "results.jsonl", "subprocess.jsonl", "async/subprocess.jsonl"]
MAX_RECORDS = {{"events": 120000, "rules": 240000, "results": 120000, "subprocesses": 10000}}
TRACE_META_KEYS = ("platform_capability", "degraded_reason", "enforcement_mode", "resolved_repo_root")


def object_dict(value: object) -> JSONDict | None:
    if not isinstance(value, Mapping):
        return None
    result: JSONDict = {{}}
    for key, item in cast(Mapping[object, object], value).items():
        if isinstance(key, str):
            result[key] = item
    return result


def object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


def trim_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    if len(value) <= limit:
        return value
    return value[:limit] + "…[trimmed]"


def parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def classify(obj: Mapping[str, object]) -> str | None:
    if "command" in obj and "returncode" in obj:
        return "subprocesses"
    if "findings" in obj and isinstance(obj.get("findings"), list):
        return "results"
    if "rule_id" in obj:
        if "decision" in obj and "severity" in obj and "event_name" in obj and "session_id" in obj:
            return "rules"
        return None
    if "event_name" in obj and "session_id" in obj:
        return "events"
    return None


def trace_metadata(obj: Mapping[str, object]) -> JSONDict:
    meta: JSONDict = {{}}
    for key in TRACE_META_KEYS:
        value = obj.get(key)
        if isinstance(value, str) or value is None:
            meta[key] = value
    return meta


def project_record(obj: Mapping[str, object]) -> tuple[str, JSONDict] | None:
    category = classify(obj)
    if category == "events":
        return category, {{
            "timestamp": obj.get("timestamp", ""),
            "platform": obj.get("platform", "claude"),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "tool_name": obj.get("tool_name", ""),
            "candidate_paths": str_list(obj.get("candidate_paths")),
            "languages": str_list(obj.get("languages")),
            **trace_metadata(obj),
        }}
    if category == "rules":
        return category, {{
            "timestamp": obj.get("timestamp", ""),
            "platform": obj.get("platform", "claude"),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "tool_name": obj.get("tool_name", ""),
            "rule_id": obj.get("rule_id", ""),
            "severity": obj.get("severity", "LOW"),
            "decision": obj.get("decision"),
            "message": trim_text(obj.get("message"), 180),
            "additional_context": trim_text(obj.get("additional_context"), 180),
            "metadata": object_dict(obj.get("metadata")) or {{}},
            **trace_metadata(obj),
        }}
    if category == "results":
        findings: list[JSONDict] = []
        for finding_value in object_list(obj.get("findings")):
            finding = object_dict(finding_value)
            if finding is None:
                continue
            findings.append({{
                "rule_id": finding.get("rule_id", ""),
                "severity": finding.get("severity", "LOW"),
                "decision": finding.get("decision"),
                "message": trim_text(finding.get("message"), 180),
                "additional_context": trim_text(finding.get("additional_context"), 180),
                "metadata": object_dict(finding.get("metadata")) or {{}},
                **trace_metadata(finding),
            }})
        return category, {{
            "timestamp": obj.get("timestamp", ""),
            "platform": obj.get("platform", "claude"),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "tool_name": obj.get("tool_name", ""),
            "findings": findings,
            "errors": [text for err in object_list(obj.get("errors")) for text in [trim_text(err, 180)] if text is not None],
            "output": None,
            "skipped": bool(obj.get("skipped", False)),
            "reason": trim_text(obj.get("reason"), 180),
            **trace_metadata(obj),
        }}
    if category == "subprocesses":
        return category, {{
            "timestamp": obj.get("timestamp", ""),
            "event_name": obj.get("event_name", ""),
            "session_id": obj.get("session_id", ""),
            "command": trim_text(obj.get("command"), 180) or "",
            "cwd": trim_text(obj.get("cwd"), 120) or "",
            "returncode": obj.get("returncode", 0),
            "stdout": trim_text(obj.get("stdout"), 120) or "",
            "stderr": trim_text(obj.get("stderr"), 180) or "",
            "duration_ms": obj.get("duration_ms", 0),
        }}
    return None


def read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or not line.startswith("{{"):
                continue
            try:
                value: object = json.loads(line)
            except json.JSONDecodeError:
                continue
            record = object_dict(value)
            if record is not None:
                yield record


cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
data: dict[str, list[JSONDict]] = {{"events": [], "rules": [], "results": [], "subprocesses": []}}
seen_files: list[str] = []
raw_counts: dict[str, int] = {{"events": 0, "rules": 0, "results": 0, "subprocesses": 0}}

for fname in JSONL_FILES:
    path = LOG_DIR / fname
    if not path.exists():
        continue
    seen_files.append(fname)
    for rec in read_jsonl(path):
        timestamp = parse_ts(rec.get("timestamp"))
        if timestamp is not None and timestamp < cutoff:
            continue
        projected = project_record(rec)
        if projected is None:
            continue
        category, item = projected
        raw_counts[category] += 1
        data[category].append(item)

truncated: dict[str, int] = {{}}
for category, limit in MAX_RECORDS.items():
    over = max(0, len(data[category]) - limit)
    if over:
        truncated[category] = over
        data[category] = data[category][-limit:]

print(json.dumps({{
    "ok": True,
    "lookback_hours": LOOKBACK_HOURS,
    "loaded_at": datetime.now(timezone.utc).isoformat(),
    "log_host": "{SSH_HOST}",
    "log_dir": str(LOG_DIR),
    "files": seen_files,
    "counts_raw": raw_counts,
    "counts_published": {{key: len(value) for key, value in data.items()}},
    "truncated": truncated,
    "data": data,
}}, separators=(",", ":")))
"""
    try:
        r = _ssh_python(script, timeout=SNAPSHOT_TIMEOUT_SECONDS)
        if r.returncode != 0:
            return {}, f"SSH exited {r.returncode}: {r.stderr.strip()}"
        payload: object = json.loads(r.stdout)
        snapshot = _coerce_object_dict(payload)
        if snapshot is None:
            return {}, "Snapshot payload must be a JSON object"
        return snapshot, None
    except subprocess.TimeoutExpired:
        return {}, "SSH snapshot timeout"
    except json.JSONDecodeError as e:
        return {}, f"Snapshot parse error: {e}"
    except Exception as e:
        return {}, str(e)


def ssh_tail_stream(handler: http.server.SimpleHTTPRequestHandler) -> None:
    """Stream remote JSONL traces over SSE until the client disconnects."""
    proc = subprocess.Popen(
        [
            "ssh",
            "-o",
            "ConnectTimeout=5",
            SSH_HOST,
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            "import subprocess\n"
            "log_dir = Path.home() / '.config' / 'slopgate' / 'logs'\n"
            "files = [log_dir / 'events.jsonl', log_dir / 'rules.jsonl', log_dir / 'results.jsonl', log_dir / 'subprocess.jsonl', log_dir / 'async' / 'subprocess.jsonl']\n"
            "files = [p for p in files if p.exists()]\n"
            "cmd = ['stdbuf', '-oL', 'tail', '-n', '20', '-F', *map(str, files)]\n"
            "subprocess.run(cmd, check=False)\n"
            "PY",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    try:
        if proc.stdout is None:
            return
        last_heartbeat = time.monotonic()
        while True:
            line = proc.stdout.readline()
            if line:
                payload = line.strip()
                if not payload.startswith("{"):
                    continue
                handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                handler.wfile.flush()
                last_heartbeat = time.monotonic()
                continue
            if proc.poll() is not None:
                break
            if time.monotonic() - last_heartbeat >= SSE_HEARTBEAT_SECONDS:
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
                last_heartbeat = time.monotonic()
            time.sleep(1)
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


class ForceDashHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
        server: BaseServer,
    ) -> None:
        super().__init__(request, client_address, server, directory=str(CANVAS_DIR))

    def log_message(self, format: str, *args: object) -> None:
        del format, args
        if "/api/" in self.path:
            print(f"[API] {self.command} {self.path}", file=sys.stderr, flush=True)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_get()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_post()
        else:
            self.send_error(405)

    def _handle_api_get(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            config, err = ssh_read_config()
            if err:
                self._json({"error": err}, 502)
            else:
                self._json(config)
        elif parsed.path == "/api/health":
            _, err = ssh_read_config()
            self._json({"ok": True, "ssh_host": SSH_HOST, "ssh_ok": err is None, "ssh_error": err})
        elif parsed.path == "/api/harness/status":
            status, err = ssh_harness_status()
            if err:
                self._json({"ok": False, "ssh_host": SSH_HOST, "error": err}, 502)
            else:
                status["ssh_host"] = SSH_HOST
                self._json(status)
        elif parsed.path == "/api/snapshot":
            snapshot, err = ssh_trace_snapshot(_snapshot_lookback_hours(self.path))
            if err:
                self._json({"ok": False, "ssh_host": SSH_HOST, "error": err}, 502)
            else:
                self._json(snapshot)
        elif parsed.path == "/api/stream":
            self._stream_sse()
        else:
            self.send_error(404)

    def _handle_api_post(self) -> None:
        if self.path == "/api/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                patch_payload: object = json.loads(body)
                patch = _coerce_object_dict(patch_payload)
                if patch is None:
                    raise ValueError("Config patch must be a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                self._json({"error": f"Bad JSON: {e}"}, 400)
                return

            # Read-modify-write to preserve unrelated config fields
            live, err = ssh_read_config()
            if err:
                self._json({"error": f"Could not read config before write: {err}"}, 502)
                return

            # Apply patch — only touch keys the client sent
            if "enabled_rules" in patch:
                existing = _coerce_bool_dict(live.get("enabled_rules"))
                existing.update(_coerce_bool_dict(patch["enabled_rules"]))
                live["enabled_rules"] = existing
            if "regex_rules" in patch and isinstance(patch["regex_rules"], list):
                live["regex_rules"] = cast(list[object], patch["regex_rules"])
            if "skip_paths" in patch:
                live["skip_paths"] = _coerce_str_list(patch["skip_paths"])

            err = ssh_write_config(live)
            if err:
                self._json({"error": err}, 502)
            else:
                self._json({"ok": True})
        else:
            self.send_error(404)

    def _json(self, data: Mapping[str, object], status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _stream_sse(self) -> None:
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self._cors()
            self.end_headers()
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            ssh_tail_stream(self)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    if not CANVAS_DIR.exists():
        print(f"Canvas dir not found: {CANVAS_DIR}", file=sys.stderr)
        sys.exit(1)
    server = http.server.ThreadingHTTPServer((BIND, PORT), ForceDashHandler)
    print(f"ForceDash  http://{BIND}:{PORT}/", file=sys.stderr, flush=True)
    print(f"Config API http://{BIND}:{PORT}/api/config  (SSH → {SSH_HOST}:{CONFIG_PATH})", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
