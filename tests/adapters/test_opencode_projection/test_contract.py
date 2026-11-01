from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, strategies

from slopgate._types import object_dict, object_list
from slopgate.adapters.opencode_projection import (
    ProjectionRequest,
    normalize_projected_tool_input,
    project_opencode_tool_input,
)
from slopgate.adapters.opencode_projection.models import PatchSection, ProjectedFile
from slopgate.adapters.opencode_projection.patch import apply_update, parse_patch
from .support import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    UNKNOWN_TOOL_INPUTS,
    projection_for,
    write_source,
)

_UNTRUSTED_MUTATIONS = [
    pytest.param(
        "apply_patch", {"patchText": "not a patch"}, "invalid", id="invalid-patch"
    ),
    pytest.param(
        "edit", {"filePath": "missing.py"}, "invalid", id="missing-edit-fields"
    ),
    pytest.param(
        "custom_mutator", {"path": "src/app.py"}, "unsupported", id="custom-tool"
    ),
]


def test_versioned_write_projects_complete_content_without_existing_file(
    tmp_path: Path,
) -> None:
    projection = projection_for(
        tmp_path, "write", {"filePath": "src/new.py", "content": "VALUE = 1\n"}
    )
    files = object_list(projection.get("files"))

    assert projection["status"] == "projected", "versioned write should be trustworthy"
    assert files == [
        {
            "path": "src/new.py",
            "content": "VALUE = 1\n",
            "operation": "write",
            "preimage_sha256": None,
        }
    ], "write projection should preserve the full replacement content"
    assert not (tmp_path / "src/new.py").exists(), (
        "projection must not mutate the workspace"
    )


def test_versioned_edit_projects_exact_replacement_from_current_state(
    tmp_path: Path,
) -> None:
    source = write_source(tmp_path, "src/app.py", "VALUE = 1\n")
    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "oldString": "VALUE = 1",
            "newString": "VALUE = 2",
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projection["status"] == "projected", "exact edit should project safely"
    assert projected["content"] == "VALUE = 2\n", (
        "edit should expose the full future file"
    )
    assert isinstance(projected["preimage_sha256"], str), (
        "edit should fingerprint current state"
    )
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n", (
        "projection must be read-only"
    )


def test_omo_hashline_edit_projects_exact_replacement_without_mutation(
    tmp_path: Path,
) -> None:
    source = write_source(tmp_path, "src/app.py", "class LintHeader:\n")
    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [{"op": "replace", "pos": "1#PS", "lines": ["class Header:"]}],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projection["status"] == "projected", (
        "fresh OMO hashline edits should project"
    )
    assert projected["content"] == "class Header:\n"
    assert source.read_text(encoding="utf-8") == "class LintHeader:\n"


def test_omo_hashline_edits_apply_against_original_snapshot_bottom_up(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "src/app.py", "class LintHeader:\n    lint_version: str\n")
    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [
                {"op": "replace", "pos": "1#PS", "lines": ["class Header:"]},
                {"op": "replace", "pos": "2#RQ", "lines": ["    version: str"]},
            ],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projection["status"] == "projected", "multiple fresh anchors should project"
    assert projected["content"] == "class Header:\n    version: str\n"


def test_omo_hashline_append_uses_anchor_as_original_snapshot_position(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "src/app.py", "class LintHeader:\n")
    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [{"op": "append", "pos": "1#PS", "lines": ["class Footer:"]}],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projection["status"] == "projected", "anchored append should project"
    assert projected["content"] == "class LintHeader:\nclass Footer:\n"


@pytest.mark.parametrize(
    "edit",
    [
        {"op": "replace", "pos": "1#ZZ", "lines": ["changed"]},
        {"op": "delete", "pos": "1#PS", "lines": []},
        {"op": "replace", "pos": "1#PS", "lines": [1]},
    ],
    ids=["stale-anchor", "unsupported-operation", "non-string-line"],
)
def test_omo_hashline_invalid_edits_remain_unprojected(
    tmp_path: Path, edit: dict[str, object]
) -> None:
    write_source(tmp_path, "src/app.py", "class LintHeader:\n")

    projection = projection_for(
        tmp_path,
        "edit",
        {"filePath": "src/app.py", "edits": [edit]},
    )

    assert projection["status"] == "invalid", (
        "stale and unsupported OMO edits must remain fail-closed"
    )


def test_versioned_apply_patch_projects_multiple_files_without_mutation(
    tmp_path: Path,
) -> None:
    source = write_source(tmp_path, "src/app.py", "VALUE = 1\n")
    patch_text = """*** Begin Patch
*** Update File: src/app.py
@@
-VALUE = 1
+VALUE = 2
*** Add File: src/new.py
+NEW_VALUE = 3
*** End Patch"""

    projection = projection_for(tmp_path, "apply_patch", {"patchText": patch_text})
    files = [object_dict(item) for item in object_list(projection.get("files"))]

    assert projection["status"] == "projected", "valid multi-file patch should project"
    assert [(item["path"], item["content"], item["operation"]) for item in files] == [
        ("src/app.py", "VALUE = 2\n", "update"),
        ("src/new.py", "NEW_VALUE = 3\n", "add"),
    ], "each patch target should receive its own complete projected content"
    assert source.read_text(encoding="utf-8") == "VALUE = 1\n", (
        "patch projection must be read-only"
    )
    assert not (tmp_path / "src/new.py").exists(), (
        "add projection must not create files"
    )


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "expected_status"),
    _UNTRUSTED_MUTATIONS,
)
def test_untrusted_mutations_never_receive_projected_status(
    tmp_path: Path,
    tool_name: str,
    tool_input: dict[str, object],
    expected_status: str,
) -> None:
    projection = projection_for(tmp_path, tool_name, tool_input)
    assert projection["status"] == expected_status, (
        "invalid and unknown-effect operations must not be classified as safe"
    )


def test_projection_public_contract_returns_complete_write_metadata(
    tmp_path: Path,
) -> None:
    request = ProjectionRequest(
        tool_name="write",
        tool_input={"filePath": "new.py", "content": "VALUE = 1\n"},
        root=tmp_path,
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )
    projection = project_opencode_tool_input(request)
    normalized = normalize_projected_tool_input(request)

    assert projection["status"] == "projected", (
        "public projection should trust a valid write"
    )
    assert normalized["edits"] == [{"file_path": "new.py", "content": "VALUE = 1\n"}], (
        "normalization should expose complete content through the canonical edits seam"
    )


def test_patch_primitives_preserve_typed_sections_and_apply_exact_updates() -> None:
    sections = parse_patch(
        "*** Begin Patch\n*** Update File: app.py\n@@\n-VALUE = 1\n+VALUE = 2\n*** End Patch"
    )

    assert sections is not None, "valid patch text should produce typed sections"
    assert isinstance(sections[0], PatchSection), (
        "parsed sections should retain their model type"
    )
    assert apply_update("VALUE = 1\n", sections[0].lines) == "VALUE = 2\n", (
        "an exact update section should produce the complete future content"
    )
    serialized = ProjectedFile("app.py", "VALUE = 2\n", "update", "digest").to_dict()
    assert serialized["path"] == "app.py", (
        "projected files should serialize their relative path"
    )


def test_normalized_delete_preserves_candidate_path(tmp_path: Path) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1\n")
    request = ProjectionRequest(
        tool_name="apply_patch",
        tool_input={
            "patchText": ("*** Begin Patch\n*** Delete File: src/app.py\n*** End Patch")
        },
        root=tmp_path,
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )

    normalized = normalize_projected_tool_input(request)

    assert normalized["edits"] == [
        {"file_path": "src/app.py", "operation": "delete"}
    ], "delete projections must retain the target path for policy enforcement"


def test_patch_rejects_duplicate_target_sections(tmp_path: Path) -> None:
    write_source(tmp_path, "app.py", "VALUE = 1\n")
    patch_text = """*** Begin Patch
*** Update File: app.py
@@
-VALUE = 1
+VALUE = 2
*** Update File: app.py
@@
-VALUE = 2
+VALUE = 3
*** End Patch"""

    projection = projection_for(tmp_path, "apply_patch", {"patchText": patch_text})

    assert projection["status"] == "invalid", (
        "a patch with repeated target sections must not be classified as projected"
    )


def test_apply_update_rejects_substring_only_match() -> None:
    result = apply_update(
        "PREFIX VALUE = 1 SUFFIX\n",
        ("@@", "-VALUE = 1", "+VALUE = 2"),
    )

    assert result is None, "patch updates must match complete source lines"


@given(strategies.text())
def test_parse_patch_never_returns_untyped_sections(text: str) -> None:
    sections = parse_patch(text)
    assert sections is None or all(
        isinstance(item, PatchSection) for item in sections
    ), "arbitrary patch text must be rejected or parsed into typed sections"


@given(strategies.text(alphabet=strategies.characters(blacklist_characters="\n\r")))
def test_apply_update_exact_token_preserves_replacement(replacement: str) -> None:
    result = apply_update("TOKEN\n", ("@@", "-TOKEN", f"+{replacement}"))
    assert result == f"{replacement}\n", (
        "an exact unique token update must preserve arbitrary replacement text"
    )


@given(UNKNOWN_TOOL_INPUTS)
def test_normalize_unknown_tool_preserves_input(
    input_values: dict[str, object],
) -> None:
    request = ProjectionRequest(
        tool_name="unknown_mutator",
        tool_input=input_values,
        root=Path.cwd(),
        contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
    )
    normalized = normalize_projected_tool_input(request)
    assert all(normalized.get(key) == value for key, value in input_values.items()), (
        "normalization must preserve arbitrary input for unsupported tools"
    )
