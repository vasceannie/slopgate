"""Remote slopgate config read, patch, and write operations."""
import json
import subprocess

from forcedash_server.remote import run_remote_python
from forcedash_server.types import JSONDict, coerce_bool_dict, coerce_object_dict, coerce_str_list

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


def apply_config_patch(live: JSONDict, patch: JSONDict) -> JSONDict:
    if "enabled_rules" in patch:
        existing = coerce_bool_dict(live.get("enabled_rules"))
        existing.update(coerce_bool_dict(patch["enabled_rules"]))
        live["enabled_rules"] = existing
    if "regex_rules" in patch and isinstance(patch["regex_rules"], list):
        live["regex_rules"] = patch["regex_rules"]
    if "skip_paths" in patch:
        live["skip_paths"] = coerce_str_list(patch["skip_paths"])
    return live
