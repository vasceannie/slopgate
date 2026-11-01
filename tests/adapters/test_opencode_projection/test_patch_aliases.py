from __future__ import annotations

from pathlib import Path

from slopgate.adapters.opencode_projection import (
    ProjectionRequest,
    normalize_projected_tool_input,
)
from .support import OPENCODE_TOOL_CONTRACT_VERSION


def test_move_patch_projects_source_delete_and_destination_add(tmp_path: Path) -> None:
    source = tmp_path / "old.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    patch_text = """*** Begin Patch
*** Update File: old.py
*** Move to: new.py
@@
-VALUE = 1
+VALUE = 2
*** End Patch"""
    request = ProjectionRequest(
        tool_name="patch",
        tool_input={"patchText": patch_text},
        root=tmp_path,
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )

    normalized = normalize_projected_tool_input(request)

    assert normalized["edits"] == [
        {"file_path": str(source.resolve()), "operation": "delete"},
        {"file_path": str(tmp_path.resolve() / "new.py"), "content": "VALUE = 2\n"},
    ], "move patches must expose both filesystem effects"
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n", (
        "move projection must not mutate the source"
    )
    assert not (tmp_path / "new.py").exists(), (
        "move projection must not create the destination"
    )
