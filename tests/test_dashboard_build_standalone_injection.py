"""Guard inline-script injection against HTML parser sequences in trace payloads."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast

REPO_ROOT = Path(__file__).resolve().parents[1]

HOSTILE_TOOL_OUTPUT = "before </script><script>window.pwned=1</script> after"
HOSTILE_HTML = "<!-- comment --> <script src='x'></script>"
HOSTILE_CASE = "</SCRIPT >"

PROBE = """
import json
import pathlib
import re
import sys

sys.path[:0] = ["dashboard/scripts", "."]
from build_standalone._builder import _inject_data

hostile = {
    "events": [
        {
            "tool_output": %(tool_output)r,
            "html": %(html)r,
            "case": %(case)r,
        }
    ]
}
config = {
    "enabled_rules": {"RULE-1": %(tool_output)r},
    "enabled_cli_rules": {},
    "rule_surfaces": {},
    "rule_counterparts": {},
    "regex_rules": [],
    "skip_paths": [],
}
index = pathlib.Path(sys.argv[1])
index.write_text("<html><head></head><body></body></html>", encoding="utf-8")
out = _inject_data(index, hostile, config)
blocks = re.findall(r"<script>(.*?)</script>", out, re.S)
print(
    json.dumps(
        {
            "block_count": len(blocks),
            "raw_open_tags": out.count("<script"),
            "raw_close_tags": out.count("</script"),
            "blocks": blocks,
            "hostile": json.dumps(hostile),
        }
    )
)
""" % {
    "tool_output": HOSTILE_TOOL_OUTPUT,
    "html": HOSTILE_HTML,
    "case": HOSTILE_CASE,
}


class InjectionProbe(TypedDict):
    """Result of running the builder's injection against a hostile payload."""

    block_count: int
    raw_open_tags: int
    raw_close_tags: int
    blocks: list[str]
    hostile: str


def _inject_hostile(tmp_path: Path) -> InjectionProbe:
    result = subprocess.run(
        [sys.executable, "-c", PROBE, str(tmp_path / "index.html")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return cast(InjectionProbe, json.loads(result.stdout))


def _payload_of(block: str, global_name: str) -> dict[str, object]:
    prefix = f"window.{global_name}="
    assert block.startswith(prefix), f"unexpected block prefix: {block[:40]}"
    value = json.loads(block[len(prefix) :].removesuffix(";"))
    assert isinstance(value, dict), "injected payload should deserialize to an object"
    return cast(dict[str, object], value)


def test_injected_payloads_stay_inside_their_script_blocks(tmp_path: Path) -> None:
    probe = _inject_hostile(tmp_path)
    assert probe["block_count"] == 2, "expected exactly the data and config blocks"
    assert probe["raw_open_tags"] == 2, "payload must not be able to open a script block"
    assert probe["raw_close_tags"] == 2, "payload must not be able to close a script block"
    offending = [block for block in probe["blocks"] if "<" in block]
    assert not offending, "injected payload must not contain a raw '<'"


def test_injected_payload_round_trips_without_data_loss(tmp_path: Path) -> None:
    probe = _inject_hostile(tmp_path)
    data_block, config_block = probe["blocks"]
    decoded = _payload_of(data_block, "__SLOPGATE_DATA__")
    assert json.dumps(decoded) == probe["hostile"], "escaping must not alter the payload"
    assert json.dumps(HOSTILE_TOOL_OUTPUT) in json.dumps(decoded), (
        "hostile text must survive as data rather than be stripped"
    )
    config = _payload_of(config_block, "__SLOPGATE_CONFIG__")
    assert config["enabled_rules"] == {"RULE-1": HOSTILE_TOOL_OUTPUT}
