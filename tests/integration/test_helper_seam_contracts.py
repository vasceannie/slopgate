from __future__ import annotations

from pathlib import Path

from tests.test_enrichment_public_api import context_for_source
from slopgate._types import object_dict
from slopgate.adapters.base import (
    hook_specific_context_output,
    render_permission_request_output,
)
from slopgate.enrichment._helpers import first_target_content, safe_read
from slopgate.lint._updater import render_slopgate_toml
from slopgate.util.payloads._patches import parse_patch_candidate_paths


def _adapter_permission_pipeline_summary() -> dict[str, object]:
    context_output = hook_specific_context_output("PreToolUse", "read files first")
    decision_output = render_permission_request_output(
        "PermissionRequest",
        "deny",
        "blocked by rule",
    )
    if decision_output is None:
        raise AssertionError("expected permission decision output")
    context_specific = object_dict(context_output.get("hookSpecificOutput"))
    decision_specific = object_dict(decision_output.get("hookSpecificOutput"))
    decision = object_dict(decision_specific.get("decision"))
    return {
        "context": context_specific.get("additionalContext"),
        "decision": decision.get("behavior"),
        "message": decision.get("message"),
    }


def test_enrichment_helper_pipeline_reads_context_and_files(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.py"
    source_path.write_text("VALUE = 1\n", encoding="utf-8")
    ctx = context_for_source(tmp_path, "VALUE = 2\n", path="sample.py")

    observed = {
        "target": first_target_content(ctx),
        "file": safe_read(source_path),
        "missing": safe_read(tmp_path / "missing.py"),
    }

    assert observed == {
        "target": "VALUE = 2\n",
        "file": "VALUE = 1\n",
        "missing": "",
    }


def test_adapter_permission_pipeline_renders_context_and_decisions() -> None:
    assert callable(hook_specific_context_output)
    assert callable(render_permission_request_output)
    assert _adapter_permission_pipeline_summary() == {
        "context": "read files first",
        "decision": "deny",
        "message": "blocked by rule",
    }


def test_lint_update_and_patch_pipeline_render_expected_contracts() -> None:
    patch_blob = """
diff --git a/src/old.py b/src/new.py
--- a/src/old.py
+++ b/src/new.py
@@
""".lstrip()

    observed = {
        "config_has_version": 'version = "9.9.9"'
        in render_slopgate_toml(version="9.9.9"),
        "paths": parse_patch_candidate_paths(patch_blob),
    }

    assert observed == {
        "config_has_version": True,
        "paths": ["src/old.py", "src/new.py"],
    }
