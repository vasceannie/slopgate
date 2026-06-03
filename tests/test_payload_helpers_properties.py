from __future__ import annotations

from pathlib import Path

from hypothesis import example, given
from hypothesis import strategies

from vibeforcer.config import load_config
from vibeforcer.lint._detectors.code_smells import detect_god_classes
from vibeforcer.util.payloads import (
    HookPayload,
    any_path_matches,
    detect_language,
    extract_content_from_mapping,
    extract_path_from_mapping,
    first_present,
    path_matches_glob,
)
from vibeforcer.util.payloads._properties import HookPayloadProperties


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@given(
    first=strategies.text(min_size=1).filter(lambda value: bool(value.strip())),
    second=strategies.text(),
)
def test_first_present_returns_first_non_blank_string(first: str, second: str) -> None:
    mapping = {"empty": "   ", "first": first, "second": second}

    assert first_present(mapping, ("missing", "empty", "first", "second")) == first.strip()


@given(
    path=strategies.from_regex(
        r"(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py",
        fullmatch=True,
    )
)
def test_path_glob_matching_is_case_insensitive_for_python_paths(path: str) -> None:
    assert {
        "language": detect_language(path.upper()),
        "basename_match": path_matches_glob(path.upper(), "*.PY"),
        "any_empty": any_path_matches(path, []),
    } == {
        "language": "python",
        "basename_match": True,
        "any_empty": True,
    }


@example(path="src/0.py", content="\r")
@given(
    path=strategies.from_regex(r"src/[A-Za-z0-9_/-]+\.py", fullmatch=True),
    content=strategies.text(),
)
def test_mapping_extractors_prefer_known_path_and_content_keys(path: str, content: str) -> None:
    payload = {"file_path": path, "new_string": content, "ignored": "nope"}

    assert {
        "path": extract_path_from_mapping(payload),
        "content": extract_content_from_mapping(payload),
    } == {
        "path": path,
        "content": content,
    }


def test_hook_payload_preserves_core_properties(tmp_path: Path) -> None:
    repo_root = tmp_path.resolve()
    payload = HookPayload(
        {
            "hook_event_name": " PreToolUse ",
            "tool_name": " Bash ",
            "session_id": 123,
            "cwd": str(repo_root / "subdir"),
            "prompt": "ship it",
            "tool_input": {
                "command": "python3 src/app.py",
                "file_path": "src/app.py",
                "content": "print('hi')",
            },
        },
        load_config(repo_root, repo_root=repo_root, ensure_enrollment=False, ensure_trace=False),
    )

    assert {
        "event_name": payload.event_name,
        "tool_name": payload.tool_name,
        "cwd": payload.cwd,
        "session_id": payload.session_id,
        "user_prompt": payload.user_prompt,
    } == {
        "event_name": "PreToolUse",
        "tool_name": "Bash",
        "cwd": repo_root / "subdir",
        "session_id": "123",
        "user_prompt": "ship it",
    }


def test_hook_payload_preserves_shell_and_target_properties(tmp_path: Path) -> None:
    repo_root = tmp_path.resolve()
    payload = HookPayload(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "cwd": str(repo_root),
            "tool_input": {
                "command": "python3 src/app.py",
                "file_path": "src/app.py",
                "content": "print('hi')",
            },
        },
        load_config(repo_root, repo_root=repo_root, ensure_enrollment=False, ensure_trace=False),
    )

    assert {
        "shell_kind": payload.shell_kind,
        "shell_command": payload.shell_command,
        "languages": payload.languages,
        "content_targets": [
            (target.path, target.content, target.source) for target in payload.content_targets
        ],
    } == {
        "shell_kind": "bash",
        "shell_command": "python3 src/app.py",
        "languages": {"python"},
        "content_targets": [("src/app.py", "print('hi')", "tool_input")],
    }


def test_hook_payload_uses_properties_mixin() -> None:
    assert issubclass(HookPayload, HookPayloadProperties)


def test_hook_payload_properties_module_has_no_god_class_regression() -> None:
    source_path = PROJECT_ROOT / "src/vibeforcer/util/payloads/_properties.py"

    violations = [
        violation
        for violation in detect_god_classes([source_path])
        if violation.identifier == "HookPayloadProperties"
    ]

    assert violations == []


def test_hook_context_module_has_no_god_class_regression() -> None:
    source_path = PROJECT_ROOT / "src/vibeforcer/context.py"

    violations = [
        violation
        for violation in detect_god_classes([source_path])
        if violation.identifier == "HookContext"
    ]

    assert violations == []
