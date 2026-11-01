from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from slopgate._types import object_dict, object_list
from slopgate.adapters.opencode_projection import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    ProjectionRequest,
    normalize_projected_tool_input,
)
from slopgate.adapters.opencode_projection.hashline import line_hash
from slopgate.util.payloads.targets import multi_edit_content_targets

from .support import projection_for, write_source


def test_omo_delete_mode_projects_existing_source_delete_with_preimage(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1\n")

    projection = projection_for(
        tmp_path,
        "edit",
        {"filePath": "src/app.py", "delete": True, "edits": []},
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projection["status"] == "projected", (
        "native delete mode should project an existing source file"
    )
    assert projected == {
        "path": "src/app.py",
        "content": "",
        "operation": "delete",
        "preimage_sha256": hashlib.sha256(b"VALUE = 1\n").hexdigest(),
    }, "delete projection must preserve the source preimage"


@pytest.mark.parametrize(
    "tool_input",
    [
        pytest.param(
            {
                "filePath": "src/app.py",
                "delete": True,
                "edits": [],
                "rename": "src/new.py",
            },
            id="delete-with-rename",
        ),
        pytest.param(
            {
                "filePath": "src/app.py",
                "delete": True,
                "edits": [
                    {
                        "op": "replace",
                        "pos": f"1#{line_hash(1, 'VALUE = 1')}",
                        "lines": ["VALUE = 2"],
                    }
                ],
            },
            id="delete-with-edits",
        ),
    ],
)
def test_omo_delete_mode_rejects_rename_and_nonempty_edits(
    tmp_path: Path,
    tool_input: dict[str, object],
) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1\n")

    projection = projection_for(tmp_path, "edit", tool_input)

    assert projection["status"] == "invalid", (
        "native-invalid delete combinations must fail closed"
    )
    assert projection["files"] == [], "invalid delete modes must have no effects"


def test_omo_rename_projects_edited_destination_and_source_delete(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1\n")
    anchor = f"1#{line_hash(1, 'VALUE = 1')}"

    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [{"op": "replace", "pos": anchor, "lines": ["VALUE = 2"]}],
            "rename": "src/new.py",
        },
    )
    files = [object_dict(item) for item in object_list(projection.get("files"))]

    assert projection["status"] == "projected", (
        "native rename-after-edit should project both filesystem effects"
    )
    assert [(item["path"], item["content"], item["operation"]) for item in files] == [
        ("src/app.py", "", "delete"),
        ("src/new.py", "VALUE = 2\n", "add"),
    ], "rename projection must preserve source deletion and edited destination"


def test_omo_rename_content_targets_preserve_both_filesystem_effects(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1\n")
    request = ProjectionRequest(
        tool_name="edit",
        tool_input={
            "filePath": "src/app.py",
            "edits": [
                {
                    "op": "replace",
                    "pos": f"1#{line_hash(1, 'VALUE = 1')}",
                    "lines": ["VALUE = 2"],
                }
            ],
            "rename": "src/new.py",
        },
        root=tmp_path,
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )

    normalized = normalize_projected_tool_input(request)
    targets = multi_edit_content_targets(normalized, "")

    assert [(target.path, target.content) for target in targets] == [
        ("src/app.py", ""),
        ("src/new.py", "VALUE = 2\n"),
    ], "ContentTarget normalization must retain delete and add paths"
