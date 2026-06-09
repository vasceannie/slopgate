"""Remote harness installation status projection."""
import json
import subprocess

from forcedash_server.remote import run_remote_python
from forcedash_server.resources import read_remote_script
from forcedash_server.types import JSONDict, coerce_object_dict

HARNESS_STATUS_SCRIPT = "harness_status.py.txt"


def harness_status() -> tuple[JSONDict, str | None]:
    try:
        result = run_remote_python(read_remote_script(HARNESS_STATUS_SCRIPT))
    except subprocess.TimeoutExpired:
        return {}, "SSH timeout"
    except OSError as exc:
        return {}, str(exc)
    if result.returncode != 0:
        return {}, f"SSH exited {result.returncode}: {result.stderr.strip()}"
    return parse_harness_payload(result.stdout)


def parse_harness_payload(stdout: str) -> tuple[JSONDict, str | None]:
    try:
        payload: object = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {}, f"Harness status parse error: {exc}"
    status = coerce_object_dict(payload)
    if status is None:
        return {}, "Harness status payload must be a JSON object"
    return status, None
