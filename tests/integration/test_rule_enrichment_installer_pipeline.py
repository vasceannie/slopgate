from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from hypothesis import given, strategies as st

from vibeforcer.enrichment._helpers import append_enrichment_message, resolve_path
from vibeforcer.enrichment.fixtures import discover_fixtures, find_parametrize_examples
from vibeforcer.context import build_context
from vibeforcer.engine._render import render_output
from vibeforcer.installer._shared import (
    filter_owned_hook_commands,
    hook_command,
    merge_owned_hooks,
    remove_owned_hooks,
    shell_command,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.common._shell_read import command_has_word, is_safe_read_shell_command
from vibeforcer.rules.python_ast._helpers import parse_module


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


def test_enrichment_pipeline_appends_messages_and_resolves_paths(tmp_path: Path) -> None:
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
        "posix": shell_command(["/tmp/Vibeforcer Bin/vibeforcer", "handle"]),
        "windows": "powershell.exe" in shell_command(["C:/Program Files/vf.exe", "handle"], windows=True),
    } == {
        "posix": "'/tmp/Vibeforcer Bin/vibeforcer' handle",
        "windows": True,
    }


def test_shell_read_pipeline_detects_standalone_command_words() -> None:
    assert {
        "rg_token": command_has_word("rg needle src/vibeforcer", "rg"),
        "substring_not_token": command_has_word("target --help", "tar"),
        "safe_null_redirect": is_safe_read_shell_command("rg needle src 2>/dev/null"),
        "unsafe_redirect": is_safe_read_shell_command("rg needle src > report.txt"),
    } == {
        "rg_token": True,
        "substring_not_token": False,
        "safe_null_redirect": True,
        "unsafe_redirect": False,
    }


def test_installer_hook_pipeline_filters_only_vibeforcer_owned_commands() -> None:
    owned = {"command": hook_command("vibeforcer", "handle", "--platform", "claude")}
    external = {"command": "echo keep-me"}
    entry = {"matcher": "Write", "hooks": [owned, external]}
    managed = {"PreToolUse": [{"matcher": "Write", "hooks": [owned]}]}

    filtered = filter_owned_hook_commands(entry)
    merged = merge_owned_hooks({"PreToolUse": [entry]}, managed)
    removed = remove_owned_hooks({"PreToolUse": [entry]})

    assert {
        "filtered": filtered,
        "merged_hooks": merged["PreToolUse"],
        "removed": removed,
    } == {
        "filtered": {"matcher": "Write", "hooks": [external]},
        "merged_hooks": [{"matcher": "Write", "hooks": [external]}, managed["PreToolUse"][0]],
        "removed": {"PreToolUse": [{"matcher": "Write", "hooks": [external]}]},
    }


def test_fixture_enrichment_pipeline_discovers_parent_fixtures_and_examples(
    tmp_path: Path,
) -> None:
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
    test_file.write_text("def test_target(root_case, local_case):\n    assert root_case\n", encoding="utf-8")
    (nested / "test_examples.py").write_text(
        "import pytest\n\n@pytest.mark.parametrize('value', [1, 2])\ndef test_value(value):\n    assert value\n",
        encoding="utf-8",
    )

    fixtures = discover_fixtures(test_file, tmp_path)
    examples = find_parametrize_examples(test_file, tmp_path)

    assert {
        "fixtures": fixtures,
        "example_file": examples[0]["file"],
        "example_snippet_has_parametrize": "parametrize" in examples[0]["snippet"],
    } == {
        "fixtures": [
            {"name": "local_case", "conftest": "tests/unit/conftest.py", "has_params": False},
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


def test_render_output_pipeline_orders_denial_context_before_advisory_debt(
    tmp_path: Path,
) -> None:
    rendered = _rendered_text(render_output(_render_context(tmp_path), _render_findings()))

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
