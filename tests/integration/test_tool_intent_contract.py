from __future__ import annotations

from hypothesis import given, strategies

from slopgate.adapters import get_adapter
from slopgate.util.payloads import (
    find_command_has_mutation,
    platform_event_name,
    shell_command_paths,
    shell_write_redirection_paths,
)
from slopgate.util.payloads._shell_paths import (
    append_unique_shell_path,
    powershell_candidate_paths,
    shell_redirection_paths,
    shell_token_path_candidates,
)
from slopgate.util.payloads._shell_script_writes import script_api_write_paths


def test_platform_event_name_preserves_opencode_source_event() -> None:
    normalized = get_adapter("opencode").normalize_payload(
        {"session_id": "integration-intent", "hook_event_name": "file.edited"}
    )

    assert platform_event_name(normalized) == "file.edited", "source event kept"


def test_find_command_has_mutation_flags_find_delete() -> None:
    tokens = ["find", ".", "-name", "*.py", "-delete"]

    assert find_command_has_mutation(tokens), "find -delete should mutate"


def test_shell_command_paths_extracts_only_proven_interpreter_write_targets() -> None:
    read_paths = shell_command_paths(
        "python -c 'print(open(\"slopgate.toml\").read())'"
    )
    write_paths = shell_command_paths(
        "python -c 'from pathlib import Path; "
        'Path("slopgate.toml").write_text("x")\''
    )

    assert read_paths == [], "interpreter read snippets are not target paths"
    assert write_paths == ["slopgate.toml"], "write API targets are preserved"


def test_shell_write_redirection_paths_extracts_redirect_targets_only() -> None:
    paths = shell_write_redirection_paths("printf x > slopgate.toml 2> /dev/null")

    assert paths == ["slopgate.toml"], "only file write redirects are targets"


def test_shell_path_helper_contracts_cover_extracted_modules() -> None:
    seen: list[str] = []
    append_unique_shell_path(seen, "app.py")

    helper_outputs = {
        "append_unique": seen,
        "option_value": shell_token_path_candidates("--config=pyproject.toml"),
        "shell_redirects": shell_redirection_paths("cat < input.txt > output.txt"),
        "powershell": powershell_candidate_paths("Get-Content -Path src/app.py"),
        "script_write": script_api_write_paths(
            'Path("slopgate.toml").write_text("x")'
        ),
    }

    assert helper_outputs == {
        "append_unique": ["app.py"],
        "option_value": ["pyproject.toml"],
        "shell_redirects": ["input.txt", "output.txt"],
        "powershell": ["src/app.py"],
        "script_write": ["slopgate.toml"],
    }


@given(
    prefix=strategies.sampled_from(["echo x", "printf x", "cat file.txt"]),
    sink=strategies.sampled_from(["> /dev/null", "2> /dev/null", "> nul", "> &1"]),
)
def test_shell_write_redirection_paths_ignores_allowed_sinks(
    prefix: str, sink: str
) -> None:
    assert shell_write_redirection_paths(f"{prefix} {sink}") == []
