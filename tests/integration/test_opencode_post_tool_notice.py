"""A post-tool block reaches the model through the result it reads."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict
from tests.integration.opencode_plugin_v2_support import (
    REPAIR_CLEAN,
    ScriptedRepo,
    run_scripted_plugin,
)

pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")

_BLOCK_REASON = "Touched-file lint detectors found issues"
_BLOCK = json.dumps({"action": "block", "reason": _BLOCK_REASON})
_WARN = json.dumps({"action": "warn", "reason": "advisory only"})
_BLOCKED_REPO = ScriptedRepo(handle=_BLOCK)
_CREATED: ObjectDict = {"content": "Created file"}
_AFTER_ERROR = """const { Error: ToolError } = await import("@opencode/plugin/promise/tool")
const event = {
  tool: "write",
  sessionID: "session",
  agent: "build",
  messageID: "message",
  id: "call",
  input: { path: "a.py", content: "x" },
  status: "error",
  error: new ToolError({ message: "disk full" }),
}
await __slopgateHooks["execute.after"](event)
console.log(JSON.stringify({ message: event.error.message }))
"""


def _after_completed(result: ObjectDict) -> str:
    return f"""const event = {{
  tool: "write",
  sessionID: "session",
  agent: "build",
  messageID: "message",
  id: "call",
  input: {{ path: "a.py", content: "x" }},
  status: "completed",
  result: {json.dumps(result)},
}}
await __slopgateHooks["execute.after"](event)
console.log(JSON.stringify(event.result))
"""


def _text_parts(result: ObjectDict) -> list[str]:
    content = result["content"]
    assert isinstance(content, list), f"content must be normalized: {result!r}"
    return [str(object_dict(part)["text"]) for part in content]


def _notice(tmp_path: Path, repo: ScriptedRepo = _BLOCKED_REPO) -> str:
    updated = run_scripted_plugin(tmp_path, _after_completed(_CREATED), repo)
    return _text_parts(updated)[-1]


_RESULT_SHAPES = (
    pytest.param({"content": "Created file"}, "Created file", id="string-content"),
    pytest.param(
        {"content": [{"type": "text", "text": "Created file"}]},
        "Created file",
        id="array-content",
    ),
    pytest.param({"output": "raw output"}, "raw output", id="output-only"),
    pytest.param({"output": {"ok": 1}}, '{"ok":1}', id="structured-output"),
)


@pytest.mark.parametrize(("result", "original"), _RESULT_SHAPES)
def test_post_tool_block_keeps_the_original_result_first(
    tmp_path: Path, result: ObjectDict, original: str
) -> None:
    updated = run_scripted_plugin(tmp_path, _after_completed(result), _BLOCKED_REPO)

    assert _text_parts(updated)[0] == original, (
        "the model must still see what the tool returned"
    )


def test_post_tool_block_tells_the_model_the_reason(tmp_path: Path) -> None:
    assert _BLOCK_REASON in _notice(tmp_path), (
        "a success-looking result must carry the violation"
    )


def test_post_tool_block_says_the_call_was_not_rolled_back(tmp_path: Path) -> None:
    assert "not rolled back" in _notice(tmp_path), (
        "the model must not assume the change was prevented"
    )


def test_post_tool_block_gives_recovery_steps_when_repair_is_armed(
    tmp_path: Path,
) -> None:
    notice = _notice(tmp_path)

    assert "QUALITY-LINT-001 in a.py" in notice, "notice must name the causal finding"
    assert "slopgate_verify_repair" in notice, "notice must name the verifier"


def test_post_tool_notice_does_not_call_the_landed_write_blocked(
    tmp_path: Path,
) -> None:
    assert "do not retry this blocked mutation" not in _notice(tmp_path), (
        "the write landed, so it was not a blocked mutation"
    )


def test_post_tool_block_does_not_claim_repair_without_armed_state(
    tmp_path: Path,
) -> None:
    notice = _notice(tmp_path, ScriptedRepo(state=REPAIR_CLEAN, handle=_BLOCK))

    assert "slopgate_verify_repair" not in notice, (
        "a degraded-mode block arms nothing, so recovery steps would mislead"
    )


def test_post_tool_block_reaches_a_failed_tool_error(tmp_path: Path) -> None:
    updated = run_scripted_plugin(tmp_path, _AFTER_ERROR, _BLOCKED_REPO)

    message = str(updated["message"])
    assert message.startswith("disk full"), "the original failure must stay first"
    assert _BLOCK_REASON in message, "a failed call must also carry the violation"


_QUIET_RESPONSES = (
    pytest.param(_WARN, id="advisory"),
    pytest.param("", id="clean"),
)


@pytest.mark.parametrize("handle", _QUIET_RESPONSES)
def test_result_is_untouched_without_a_post_tool_block(
    tmp_path: Path, handle: str
) -> None:
    updated = run_scripted_plugin(
        tmp_path,
        _after_completed(_CREATED),
        ScriptedRepo(state=REPAIR_CLEAN, handle=handle),
    )

    assert updated == _CREATED, "only a block may rewrite what the model reads"
