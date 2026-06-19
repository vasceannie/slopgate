from __future__ import annotations

import ast
import re
from pathlib import Path

from slopgate.models import ContentTarget

from ._shell import shell_tokens

_HEREDOC_NAME_TEXT = r"(?P<marker>[A-Za-z_][A-Za-z0-9_]*)"
_HEREDOC_QUOTED_NAME_TEXT = rf"<<\s*['\"]?{_HEREDOC_NAME_TEXT}['\"]?"
_SHELL_PATH_TEXT = r"(?P<path>[^\s;&|]+)"
_CAT_REDIRECT_HEREDOC_RE = re.compile(
    rf"\bcat\s+>\s*{_SHELL_PATH_TEXT}\s+{_HEREDOC_QUOTED_NAME_TEXT}\s*\n"
    r"(?P<body>.*?)"
    r"\n(?P=marker)(?:\s|$)",
    re.DOTALL,
)
_CAT_TEE_HEREDOC_RE = re.compile(
    rf"\bcat\s+{_HEREDOC_QUOTED_NAME_TEXT}\s*\|\s*tee(?:\s+-a)?\s+"
    rf"{_SHELL_PATH_TEXT}\s*\n"
    r"(?P<body>.*?)"
    r"\n(?P=marker)(?:\s|$)",
    re.DOTALL,
)
_PYTHON_HEREDOC_RE = re.compile(
    rf"\bpython(?:3)?\s+-\s+{_HEREDOC_QUOTED_NAME_TEXT}\s*\n"
    r"(?P<body>.*?)"
    r"\n(?P=marker)(?:\s|$)",
    re.DOTALL,
)
_WRITE_REDIRECT_TOKENS = frozenset({">", ">>", "1>", "1>>", "&>"})
_PYTHON_EXECUTABLE_NAMES = frozenset({"python", "python3"})


def _clean_path(value: str) -> str:
    return value.strip("\"'`")


def _literal_string(node: ast.AST) -> str:
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return ""
    return value if isinstance(value, str) else ""


def _path_call_value(node: ast.AST) -> str:
    if not isinstance(node, ast.Call) or not node.args:
        return ""
    func = node.func
    if isinstance(func, ast.Name):
        is_path = func.id == "Path"
    elif isinstance(func, ast.Attribute):
        is_path = func.attr == "Path"
    else:
        is_path = False
    return _literal_string(node.args[0]) if is_path else ""


def _open_write_path(node: ast.AST) -> str:
    if not isinstance(node, ast.Call) or not node.args:
        return ""
    if not isinstance(node.func, ast.Name) or node.func.id != "open":
        return ""
    mode = "r"
    if len(node.args) >= 2:
        mode = _literal_string(node.args[1]) or mode
    for keyword in node.keywords:
        if keyword.arg == "mode":
            mode = _literal_string(keyword.value) or mode
    if not any(marker in mode for marker in ("w", "a", "x", "+")):
        return ""
    return _literal_string(node.args[0])


def _python_write_targets(script: str) -> list[ContentTarget]:
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return []
    targets: list[ContentTarget] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"write_text", "write"} and node.args:
            path_value = _path_call_value(node.func.value)
            if not path_value:
                path_value = _open_write_path(node.func.value)
            content = _literal_string(node.args[0])
            if path_value and content:
                targets.append(
                    ContentTarget(
                        path=path_value,
                        content=content,
                        source="shell_python_write",
                    )
                )
    return targets


def _python_inline_scripts(command: str) -> list[str]:
    scripts: list[str] = []
    tokens = shell_tokens(command)
    for index, token in enumerate(tokens):
        executable = Path(token.strip("\"'")).name.lower()
        if executable not in _PYTHON_EXECUTABLE_NAMES:
            continue
        for option_index in range(index + 1, len(tokens) - 1):
            if tokens[option_index] == "-c":
                scripts.append(tokens[option_index + 1])
                break
    return scripts


def _python_heredoc_scripts(command: str) -> list[str]:
    return [match.group("body") for match in _PYTHON_HEREDOC_RE.finditer(command)]


def _heredoc_content_targets(command: str) -> list[ContentTarget]:
    targets: list[ContentTarget] = []
    for pattern in (_CAT_REDIRECT_HEREDOC_RE, _CAT_TEE_HEREDOC_RE):
        for match in pattern.finditer(command):
            targets.append(
                ContentTarget(
                    path=_clean_path(match.group("path")),
                    content=match.group("body"),
                    source="shell_heredoc",
                )
            )
    return targets


def _echo_redirect_targets(command: str) -> list[ContentTarget]:
    targets: list[ContentTarget] = []
    tokens = shell_tokens(command)
    if not tokens or Path(tokens[0]).name.lower() != "echo":
        return targets
    for index, token in enumerate(tokens):
        if token not in _WRITE_REDIRECT_TOKENS or index + 1 >= len(tokens):
            continue
        path_value = _clean_path(tokens[index + 1])
        content = " ".join(tokens[1:index])
        if path_value and content:
            targets.append(
                ContentTarget(path=path_value, content=content, source="shell_echo")
            )
    return targets


def shell_content_targets(command: str) -> list[ContentTarget]:
    """Extract high-confidence proposed file content from shell write commands."""
    targets: list[ContentTarget] = []
    targets.extend(_heredoc_content_targets(command))
    targets.extend(_echo_redirect_targets(command))
    for script in [*_python_inline_scripts(command), *_python_heredoc_scripts(command)]:
        targets.extend(_python_write_targets(script))
    return targets
