from __future__ import annotations

from pathlib import Path

from slopgate.adapters.opencode_projection import (
    ProjectionRequest,
    normalize_projected_tool_input,
    project_opencode_tool_input,
)
from .support import OPENCODE_TOOL_CONTRACT_VERSION


def test_snake_case_patch_text_projects_and_preserves_original(
    tmp_path: Path,
) -> None:
    patch_text = """*** Begin Patch
*** Add File: new.py
+VALUE = 1
*** End Patch"""
    request = ProjectionRequest(
        tool_name="apply_patch",
        tool_input={"patch_text": patch_text},
        root=tmp_path,
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )

    projection = project_opencode_tool_input(request)
    normalized = normalize_projected_tool_input(request)

    assert projection["status"] == "projected", (
        "snake_case patch text should receive a filesystem projection"
    )
    assert normalized["edits"] == [
        {"file_path": "new.py", "content": "VALUE = 1\n"}
    ], "snake_case patches should expose canonical projected edits"
    assert normalized["_slopgate_original_patch_text"] == patch_text, (
        "normalization should preserve the original snake_case patch text"
    )
    assert "patch_text" not in normalized, (
        "canonical normalization should remove the native patch alias"
    )


def test_patch_rejects_conflicting_patch_text_aliases(tmp_path: Path) -> None:
    request = ProjectionRequest(
        tool_name="apply_patch",
        tool_input={
            "patchText": "*** Begin Patch\n*** End Patch",
            "patch_text": "*** Begin Patch\n*** Add File: other.py\n+VALUE = 1\n*** End Patch",
        },
        root=tmp_path,
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )

    projection = project_opencode_tool_input(request)

    assert projection["status"] == "invalid", (
        "conflicting patch aliases must not be projected ambiguously"
    )


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
        tool_name="apply_patch",
        tool_input={"patchText": patch_text},
        root=tmp_path,
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )

    normalized = normalize_projected_tool_input(request)

    assert normalized["edits"] == [
        {"file_path": "old.py", "operation": "delete"},
        {"file_path": "new.py", "content": "VALUE = 2\n"},
    ], "move patches must expose both filesystem effects"
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n", (
        "move projection must not mutate the source"
    )
    assert not (tmp_path / "new.py").exists(), (
        "move projection must not create the destination"
    )
