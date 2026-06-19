from __future__ import annotations

from slopgate.util.payloads import shell_content_targets


def test_shell_content_targets_extracts_echo_redirect_content() -> None:
    targets = shell_content_targets("echo 'from typing import Any' > src/example.py")

    assert [(target.path, target.content, target.source) for target in targets] == [
        ("src/example.py", "from typing import Any", "shell_echo")
    ], "shell_content_targets should extract echo redirect content"


def test_shell_content_targets_extracts_cat_heredoc_content() -> None:
    command = "cat > src/example.py <<'PY'\nx = y  # type: ignore[arg-type]\nPY"

    targets = shell_content_targets(command)

    assert [(target.path, target.content, target.source) for target in targets] == [
        ("src/example.py", "x = y  # type: ignore[arg-type]", "shell_heredoc")
    ], "shell_content_targets should extract heredoc redirect content"
