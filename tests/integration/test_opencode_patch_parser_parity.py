"""Differential contract between parse_patch and the pinned host Patch.parse."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from slopgate.adapters.opencode_projection.patch import parse_patch

pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")

_HOST_PATCH_MODULE = (
    Path(__file__).parents[2]
    / "node_modules"
    / "@opencode"
    / "util"
    / "dist"
    / "patch.js"
)
_HOST_PARSE_SOURCE = """
import { Patch } from %s
const result = Patch.parse(process.argv[2])
const hunks = result._tag === "Success"
  ? result.success.map((hunk) => [hunk.type, hunk.path, hunk.movePath ?? null])
  : null
process.stdout.write(JSON.stringify(hunks))
"""
_ENVELOPE = "*** Begin Patch\n%s\n*** End Patch"


def _host_sections(tmp_path: Path, patch_text: str) -> object:
    runner = tmp_path / "parse.mjs"
    runner.write_text(
        _HOST_PARSE_SOURCE % json.dumps(_HOST_PATCH_MODULE.as_uri()), encoding="utf-8"
    )
    completed = subprocess.run(
        ["bun", str(runner), patch_text],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


_HOST_ACCEPTED_BODIES = (
    pytest.param("*** Update File: a.py\n@@\n-x\n+y", id="update"),
    pytest.param("*** Add File: a.py\n+x\n*** Delete File: b.py", id="add-delete"),
    pytest.param("*** Update File: a.py\n*** Move to: b.py\n@@\n-x\n+y", id="move"),
    pytest.param(
        "*** Update File: a.py\n@@\n *** Add File: z.txt\n+evil",
        id="update-context-resembles-add-header",
    ),
    pytest.param(
        "*** Update File: a.py\n@@\n-x\n+y\n  *** Delete File: b.py",
        id="update-context-resembles-delete-header",
    ),
    pytest.param(
        "*** Update File: a.py\n@@\n-x\n+y\n*** End of File\n*** Add File: c.py\n+z",
        id="end-of-file-then-header",
    ),
    pytest.param(
        "*** Add File: a.py\n+x\n  *** Delete File: b.py",
        id="add-body-then-indented-header",
    ),
    pytest.param("*** Environment ID: e1\n*** Add File: a.py\n+x", id="environment-id"),
)


@pytest.mark.parametrize("body", _HOST_ACCEPTED_BODIES)
def test_host_accepted_patch_sections_match_python_parser(
    tmp_path: Path, body: str
) -> None:
    patch_text = _ENVELOPE % body

    sections = parse_patch(patch_text)

    assert sections is not None, "patches the host accepts must parse"
    assert [[item.operation, item.path, item.move_to] for item in sections] == (
        _host_sections(tmp_path, patch_text)
    ), "policy must see the same file sections the host applies"


def test_move_header_without_space_is_rejected_like_the_host(tmp_path: Path) -> None:
    patch_text = _ENVELOPE % "*** Update File: a.py\n*** Move to:b.py\n@@\n-x\n+y"

    sections = parse_patch(patch_text)

    assert _host_sections(tmp_path, patch_text) is None, "host contract changed"
    assert sections is None or sections[0].move_to is None, (
        "a move the host rejects must not be projected as a move"
    )
