from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from slopgate.enrichment._helpers import (
    append_enrichment_message,
    loaded_source_at_path,
    metadata_str,
    path_source_from_metadata,
    resolve_path,
)
from slopgate.constants import METADATA_PATH
from slopgate.context import HookContext, build_context
from slopgate.enrichment.fixtures import discover_fixtures, find_parametrize_examples
from slopgate.adapters.base import render_request_from_call
from slopgate.engine._render import render_output
from slopgate.installer._shared import (
    command_is_slopgate_hook,
    filter_owned_hook_commands,
    hook_command,
    merge_owned_hooks,
    remove_owned_hooks,
    shell_command,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.common._shell_safe_read import (
    command_has_word,
    is_safe_read_shell_command,
)
from slopgate.rules.python_ast._helpers import parse_module


def test_python_ast_parse_pipeline_respects_size_and_syntax_bounds() -> None:
    parsed = parse_module("def ok():\n    return 1\n", max_chars=100)

    assert {
        "parsed_type": type(parsed),
        "oversize": parse_module("x" * 10, max_chars=2),
        "syntax_error": parse_module("def broken(:\n", max_chars=100),
    } == {
        "parsed_type": ast.Module,
        "oversize": None,
        "syntax_error": None,
    }


def _enrichment_metadata_context(
    tmp_path: Path,
) -> tuple[Path, RuleFinding, HookContext]:
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    finding = RuleFinding(
        "RULE",
        "Title",
        Severity.MEDIUM,
        message="base",
        metadata={METADATA_PATH: "src/app.py"},
    )
    base_ctx = build_context(
        {
            "session_id": "enrichment-metadata",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/app.py", "content": "VALUE = 2\n"},
        }
    )
    ctx = replace(base_ctx, config=replace(base_ctx.config, root=tmp_path))
    return target, finding, ctx


def test_enrichment_metadata_helpers_load_hook_targets(tmp_path: Path) -> None:
    target, finding, ctx = _enrichment_metadata_context(tmp_path)

    assert metadata_str(finding.metadata, METADATA_PATH) == "src/app.py"
    assert loaded_source_at_path("src/app.py", ctx.config.root) == (
        target,
        "VALUE = 1\n",
    )
    assert path_source_from_metadata(finding, ctx) == (target, "VALUE = 1\n")


def test_enrichment_pipeline_appends_messages_and_resolves_paths(
    tmp_path: Path,
) -> None:
    finding = RuleFinding("RULE", "Title", Severity.MEDIUM, message="base")
    append_enrichment_message(finding, ["hint one", "hint two"])

    assert {
        "message": finding.message,
        "relative": resolve_path("src/app.py", tmp_path),
        "absolute": resolve_path(str(tmp_path / "abs.py"), tmp_path),
    } == {
        "message": "base\nhint one\nhint two",
        "relative": (tmp_path / "src/app.py").resolve(),
        "absolute": tmp_path / "abs.py",
    }


def test_installer_command_pipeline_quotes_posix_and_powershell_commands() -> None:
    assert {
        "posix": shell_command(["/tmp/Slopgate Bin/slopgate", "handle"], windows=False),
        "windows": "powershell.exe"
        in shell_command(["C:/Program Files/vf.exe", "handle"], windows=True),
    } == {
        "posix": "'/tmp/Slopgate Bin/slopgate' handle",
        "windows": True,
    }


def test_shell_read_pipeline_detects_standalone_command_words() -> None:
    assert {
        "rg_token": command_has_word("rg needle src/slopgate", "rg"),
        "substring_not_token": command_has_word("target --help", "tar"),
        "safe_null_redirect": is_safe_read_shell_command("rg needle src 2>/dev/null"),
        "unsafe_redirect": is_safe_read_shell_command("rg needle src > report.txt"),
    } == {
        "rg_token": True,
        "substring_not_token": False,
        "safe_null_redirect": True,
        "unsafe_redirect": False,
    }


def test_installer_hook_pipeline_filters_only_slopgate_owned_commands() -> None:
    owned = {"command": hook_command("slopgate", "handle", "--platform", "claude")}
    external = {"command": "echo keep-me"}
    entry = {"matcher": "Write", "hooks": [owned, external]}
    managed: dict[str, list[dict[str, object]]] = {
        "PreToolUse": [{"matcher": "Write", "hooks": [owned]}]
    }

    filtered = filter_owned_hook_commands(entry)
    merged = merge_owned_hooks({"PreToolUse": [entry]}, managed)
    removed = remove_owned_hooks({"PreToolUse": [entry]})

    assert {
        "owned": command_is_slopgate_hook(owned["command"]),
        "filtered": filtered,
        "merged_hooks": merged["PreToolUse"],
        "removed": removed,
    } == {
        "owned": True,
        "filtered": {"matcher": "Write", "hooks": [external]},
        "merged_hooks": [
            {"matcher": "Write", "hooks": [external]},
            managed["PreToolUse"][0],
        ],
        "removed": {"PreToolUse": [{"matcher": "Write", "hooks": [external]}]},
    }


def _fixture_enrichment_layout(tmp_path: Path) -> tuple[Path, Path]:
    tests_dir = tmp_path / "tests"
    nested = tests_dir / "unit"
    nested.mkdir(parents=True)
    (tests_dir / "conftest.py").write_text(
        "import pytest\n\n@pytest.fixture(params=[1, 2])\ndef root_case():\n    return 1\n",
        encoding="utf-8",
    )
    (nested / "conftest.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef local_case():\n    return 2\n",
        encoding="utf-8",
    )
    test_file = nested / "test_target.py"
    test_file.write_text(
        "def test_target(root_case, local_case):\n    assert root_case\n",
        encoding="utf-8",
    )
    (nested / "test_examples.py").write_text(
        "import pytest\n\n@pytest.mark.parametrize('value', [1, 2])\ndef test_value(value):\n    assert value\n",
        encoding="utf-8",
    )
    return test_file, tmp_path


def test_fixture_enrichment_pipeline_discovers_parent_fixtures_and_examples(
    tmp_path: Path,
) -> None:
    test_file, repo_root = _fixture_enrichment_layout(tmp_path)

    fixtures = discover_fixtures(test_file, repo_root)
    examples = find_parametrize_examples(test_file, repo_root)

    assert {
        "fixtures": fixtures,
        "example_file": examples[0]["file"],
        "example_snippet_has_parametrize": "parametrize" in examples[0]["snippet"],
    } == {
        "fixtures": [
            {
                "name": "local_case",
                "conftest": "tests/unit/conftest.py",
                "has_params": False,
            },
            {"name": "root_case", "conftest": "tests/conftest.py", "has_params": True},
        ],
        "example_file": "test_examples.py",
        "example_snippet_has_parametrize": True,
    }


def _render_context(tmp_path: Path):
    return build_context(
        {
            "session_id": "render-output-integration",
            "cwd": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/app.py"},
        }
    )


def _render_findings() -> list[RuleFinding]:
    return [
        RuleFinding(
            "DENY-RULE",
            "Blocking rule",
            Severity.HIGH,
            decision="deny",
            message="stop first",
            additional_context="immediate repair",
            updated_input={"command": "rewritten"},
        ),
        RuleFinding(
            "ADVISORY-RULE",
            "Advisory rule",
            Severity.LOW,
            message="later",
            additional_context="later cleanup",
        ),
    ]


def _rendered_text(output: object) -> str:
    assert output is not None
    return str(output)


def test_adapter_render_request_pipeline_extracts_event_and_findings() -> None:
    findings = _render_findings()
    request = render_request_from_call(
        ("PreToolUse", findings),
        {
            "context": "immediate repair",
            "updated_input": {"command": "rewritten"},
            "decision": "deny",
        },
    )

    assert {
        "event_name": request.event_name,
        "finding_count": len(request.findings),
        "decision": request.decision,
    } == {
        "event_name": "PreToolUse",
        "finding_count": 2,
        "decision": "deny",
    }


def test_render_output_pipeline_orders_denial_context_before_advisory_debt(
    tmp_path: Path,
) -> None:
    rendered = _rendered_text(
        render_output(_render_context(tmp_path), _render_findings())
    )

    assert {
        "denial_before_advisory": rendered.index("immediate repair")
        < rendered.index("later cleanup"),
        "labels_later_debt": "Later design debt / not the immediate unblock action"
        in rendered,
        "includes_rewrite": "rewritten" in rendered,
    } == {
        "denial_before_advisory": True,
        "labels_later_debt": True,
        "includes_rewrite": True,
    }
