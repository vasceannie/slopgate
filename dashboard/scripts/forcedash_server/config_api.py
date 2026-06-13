"""Remote slopgate config read, patch, and write operations."""

import json
import subprocess

from forcedash_server.remote import run_remote_python
from forcedash_server.types import (
    JSONDict,
    coerce_bool_dict,
    coerce_object_dict,
    coerce_str_list,
)
from rule_interop import load_rule_counterparts

RULE_SURFACE_ACTIONS = {"allow", "ask", "block", "context", "deny", "warn"}

READ_CONFIG_SCRIPT = (
    "from pathlib import Path\n"
    "print((Path.home() / '.config' / 'slopgate' / 'config.json').read_text())"
)
WRITE_CONFIG_SCRIPT = (
    "import sys\n"
    "from pathlib import Path\n"
    "Path.home().joinpath('.config', 'slopgate', 'config.json').write_text(sys.stdin.read())"
)


def read_config() -> tuple[JSONDict, str | None]:
    try:
        result = run_remote_python(READ_CONFIG_SCRIPT)
    except subprocess.TimeoutExpired:
        return {}, "SSH timeout"
    except OSError as exc:
        return {}, str(exc)
    if result.returncode != 0:
        return {}, f"SSH exited {result.returncode}: {result.stderr.strip()}"
    return parse_config_payload(result.stdout)


def parse_config_payload(stdout: str) -> tuple[JSONDict, str | None]:
    try:
        payload: object = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {}, f"Config parse error: {exc}"
    config = coerce_object_dict(payload)
    if config is None:
        return {}, "Config payload must be a JSON object"
    return config, None


def write_config(config: JSONDict) -> str | None:
    try:
        payload = json.dumps(config, indent=2)
        result = run_remote_python(WRITE_CONFIG_SCRIPT, input_text=payload)
    except subprocess.TimeoutExpired:
        return "SSH timeout"
    except OSError as exc:
        return str(exc)
    if result.returncode != 0:
        return f"SSH write exited {result.returncode}: {result.stderr.strip()}"
    return None


def dashboard_config(config: JSONDict) -> JSONDict:
    return {**config, "rule_counterparts": load_rule_counterparts()}


def coerce_rule_surfaces(value: object) -> JSONDict:
    source = coerce_object_dict(value)
    if source is None:
        return {}
    surfaces: JSONDict = {}
    for rule_id, item in source.items():
        surface = coerce_object_dict(item)
        if surface is None:
            continue
        coerced = _coerce_rule_surface(surface)
        if coerced:
            surfaces[rule_id] = coerced
    return surfaces


def _coerce_rule_surface(surface: JSONDict) -> JSONDict:
    result: JSONDict = {}
    hook = _coerce_hook_surface(surface.get("hook"))
    if hook:
        result["hook"] = hook
    cli = _coerce_cli_surface(surface.get("cli"))
    if cli:
        result["cli"] = cli
    return result


def _coerce_hook_surface(value: object) -> JSONDict:
    source = coerce_object_dict(value)
    if source is None:
        return {}
    result: JSONDict = {}
    if isinstance(source.get("enabled"), bool):
        result["enabled"] = source["enabled"]
    events = coerce_str_list(source.get("events"))
    if events:
        result["events"] = events
    action = source.get("action")
    if isinstance(action, str) and action in RULE_SURFACE_ACTIONS:
        result["action"] = action
    return result


def _coerce_cli_surface(value: object) -> JSONDict:
    source = coerce_object_dict(value)
    if source is None or not isinstance(source.get("enabled"), bool):
        return {}
    return {"enabled": source["enabled"]}


def merge_rule_surfaces(existing: JSONDict, patch: JSONDict) -> JSONDict:
    merged = dict(existing)
    for rule_id, item in patch.items():
        surface = coerce_object_dict(item)
        if surface is None:
            continue
        current = coerce_object_dict(merged.get(rule_id)) or {}
        next_surface = dict(current)
        for key in ("hook", "cli"):
            section = coerce_object_dict(surface.get(key))
            if section is not None:
                current_section = coerce_object_dict(current.get(key)) or {}
                next_surface[key] = {**current_section, **section}
        merged[rule_id] = next_surface
    return merged


def apply_config_patch(live: JSONDict, patch: JSONDict) -> JSONDict:
    if "enabled_rules" in patch:
        existing = coerce_bool_dict(live.get("enabled_rules"))
        existing.update(coerce_bool_dict(patch["enabled_rules"]))
        live["enabled_rules"] = existing
    if "enabled_cli_rules" in patch:
        existing_cli = coerce_bool_dict(live.get("enabled_cli_rules"))
        existing_cli.update(coerce_bool_dict(patch["enabled_cli_rules"]))
        live["enabled_cli_rules"] = existing_cli
    if "rule_surfaces" in patch:
        existing_surfaces = coerce_rule_surfaces(live.get("rule_surfaces"))
        patch_surfaces = coerce_rule_surfaces(patch["rule_surfaces"])
        live["rule_surfaces"] = merge_rule_surfaces(existing_surfaces, patch_surfaces)
    if "regex_rules" in patch and isinstance(patch["regex_rules"], list):
        live["regex_rules"] = patch["regex_rules"]
    if "skip_paths" in patch:
        live["skip_paths"] = coerce_str_list(patch["skip_paths"])
    return live
