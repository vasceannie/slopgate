from __future__ import annotations

import json
import sys
from collections.abc import Sequence

import slopgate.installer._pi


def pi_extension_template() -> str:
    from slopgate.resources import resource_path

    return resource_path("pi_extension.ts").read_text(encoding="utf-8")


def contains_markers(source: str, markers: Sequence[str], contract: str) -> bool:
    missing = [marker for marker in markers if marker not in source]
    assert not missing, f"{contract}: missing markers {missing!r}"
    return True


def excludes_markers(source: str, markers: Sequence[str], contract: str) -> bool:
    present = [marker for marker in markers if marker in source]
    assert not present, f"{contract}: unexpected markers {present!r}"
    return True


def test_pi_extension_falls_back_to_python_module_invocation() -> None:
    extension = slopgate.installer._pi.render_pi_extension(
        pi_extension_template(), sys.executable
    )
    assert contains_markers(
        extension,
        [json.dumps([sys.executable, "-m", "slopgate"])],
        "python fallback argv is rendered",
    )
    assert excludes_markers(
        extension,
        ["__SLOPGATE_BIN__", f'{json.dumps(sys.executable)}, "handle"'],
        "python fallback argv avoids invalid direct handle invocation",
    )


def test_pi_extension_uses_documented_input_event_text() -> None:
    assert contains_markers(
        pi_extension_template(),
        [
            "text?: string",
            "function promptFromEvent(event: PiEventLike): string",
            'return event.text || event.prompt || ""',
            "prompt: promptFromEvent(event)",
        ],
        "input prompt text is sourced from documented event text",
    )


def test_pi_extension_does_not_require_node_buffer_global() -> None:
    assert excludes_markers(
        pi_extension_template(),
        ["Buffer"],
        "extension does not require Node Buffer global",
    )
