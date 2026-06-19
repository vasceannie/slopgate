from __future__ import annotations

from tests.test_engine import shell_command_paths


def test_shell_command_paths_captures_redirect_targets() -> None:
    paths = shell_command_paths(
        "grep foo src/app.py>pyproject.toml && echo hi > Makefile && touch Makefile"
    )
    assert "pyproject.toml" in paths, (
        "shell_command_paths should capture compact redirect targets"
    )
    assert "Makefile" in paths, (
        "shell_command_paths should capture redirect and touch targets"
    )


def test_shell_command_paths_ignores_glob_patterns() -> None:
    paths = shell_command_paths("python -m py_compile *.py src/*.py")
    assert "*.py" not in paths, "shell_command_paths should ignore bare glob patterns"
    assert "src/*.py" not in paths, (
        "shell_command_paths should ignore path-like glob patterns"
    )


def test_shell_command_paths_ignores_paths_inside_quoted_option_text() -> None:
    paths = shell_command_paths(
        'bd close job-hunter-6vc1 --reason="Centralized parsing in '
        "src/sse_parsing.py and cloud agent_stream/sse.py; moved "
        'runtime_lifecycle.py."'
    )
    assert paths == [], (
        "shell_command_paths should ignore path-looking text inside quoted options"
    )


def test_shell_command_paths_still_captures_path_option_values() -> None:
    paths = shell_command_paths("tool --config=pyproject.toml --file src/app.py")
    assert paths == ["pyproject.toml", "src/app.py"], (
        "shell_command_paths should capture path-valued command options in order"
    )


def test_shell_command_paths_ignore_absolute_executable_position() -> None:
    paths = shell_command_paths('/usr/bin/rg -n "needle" src/app.py')
    assert paths == ["src/app.py"], (
        "shell_command_paths should ignore an absolute executable at argv position"
    )


def test_shell_command_paths_ignore_wrapped_absolute_executable_position() -> None:
    paths = shell_command_paths(
        "env FOO=bar /usr/bin/python -m pytest tests/test_app.py"
    )
    assert paths == ["tests/test_app.py"], (
        "shell_command_paths should ignore wrapped absolute Python executables"
    )
