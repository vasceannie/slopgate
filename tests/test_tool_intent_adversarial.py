from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.context import build_context
from slopgate.engine import evaluate_payload
from slopgate.util.payloads import (
    candidate_path_source,
    is_read_only_tool_use,
    tool_intent,
)
from tests.test_engine import finding_ids


def _pretool_bash_payload(cwd: Path, command: str) -> dict[str, object]:
    return {
        "session_id": "intent-adversarial-test",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def _repo_with_slopgate_toml(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")
    return repo


def _repo_with_protected_file(tmp_path: Path, file_name: str) -> Path:
    repo = _repo_with_slopgate_toml(tmp_path)
    _ = (repo / file_name).write_text("initial\n")
    return repo


def _programmable_execute_not_read_only(command: str, tmp_path: Path) -> bool:
    payload = _pretool_bash_payload(tmp_path, command)

    assert not is_read_only_tool_use(payload), (
        f"{command} should not be read-only by executable name"
    )
    assert tool_intent(payload) == "execute", f"{command} should stay execute"
    return True


def _script_write_denied(command: str, tmp_path: Path) -> bool:
    payload = _pretool_bash_payload(_repo_with_slopgate_toml(tmp_path), command)
    result = evaluate_payload(payload)

    assert tool_intent(payload) == "mutate", f"{command} should be mutating"
    assert candidate_path_source(payload) == "script_write_target"
    assert "REPO-ENROLL-001" in finding_ids(result), (
        "script writes to slopgate.toml must remain denied"
    )
    return True


def _protected_script_write_denied(
    command: str, protected_file: str, tmp_path: Path
) -> bool:
    payload = _pretool_bash_payload(
        _repo_with_protected_file(tmp_path, protected_file),
        command,
    )
    result = evaluate_payload(payload)

    assert tool_intent(payload) == "mutate", f"{command} should be mutating"
    assert candidate_path_source(payload) == "script_write_target"
    assert "BUILTIN-PROTECTED-PATHS" in finding_ids(result), (
        f"script writes to {protected_file} must be denied"
    )
    return True


def _interpreter_read_allowed(tmp_path: Path) -> bool:
    payload = _pretool_bash_payload(
        _repo_with_slopgate_toml(tmp_path),
        "python -c 'print(open(\"slopgate.toml\").read())'",
    )
    result = evaluate_payload(payload)
    ids = finding_ids(result)

    assert tool_intent(payload) == "execute", "interpreter reads stay executable"
    assert candidate_path_source(payload) != "script_write_target"
    assert build_context(payload).candidate_paths == []
    assert "REPO-ENROLL-001" not in ids, "read snippet must not trip edit guard"
    assert "BUILTIN-PROTECTED-PATHS" not in ids, (
        "read snippet must not trip protected-path edit guard"
    )
    return True


def _shell_telemetry_matches(
    command: str, expected_intent: str, expected_source: str, tmp_path: Path
) -> bool:
    payload = _pretool_bash_payload(tmp_path, command)

    assert tool_intent(payload) == expected_intent
    assert candidate_path_source(payload) == expected_source
    return True


def _mutating_shell_not_safe_read(command: str, tmp_path: Path) -> bool:
    payload = _pretool_bash_payload(tmp_path, command)

    assert not is_read_only_tool_use(payload), f"{command} must not be read-only"
    assert tool_intent(payload) == "mutate", f"{command} should be mutating"
    return True


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("awk 'BEGIN{print 1}'", id="awk"),
        pytest.param("python -c 'print(1)'", id="python"),
        pytest.param("node -e 'console.log(1)'", id="node"),
        pytest.param("ruby -e 'puts 1'", id="ruby"),
        pytest.param("perl -e 'print 1'", id="perl"),
    ],
)
def test_programmable_shell_commands_are_not_read_only(
    command: str, tmp_path: Path
) -> None:
    assert _programmable_execute_not_read_only(command, tmp_path)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "awk 'BEGIN{system(\"touch slopgate.toml\")}'",
            id="awk_system_touch",
        ),
        pytest.param(
            "python -c 'from pathlib import Path; "
            'Path("slopgate.toml").write_text("x")\'',
            id="python_write_text",
        ),
        pytest.param(
            "python -c 'from pathlib import Path; "
            'Path("slopgate.toml").write_bytes(b\"x\")\'',
            id="python_write_bytes",
        ),
        pytest.param(
            "python -c 'open(\"slopgate.toml\", \"w\").write(\"x\")'",
            id="python_open_write",
        ),
        pytest.param(
            "node -e 'require(\"fs\").writeFileSync(\"slopgate.toml\", \"x\")'",
            id="node_write_file_sync",
        ),
    ],
)
def test_interpreter_mutations_to_slopgate_toml_emit_enrollment_denial(
    command: str, tmp_path: Path
) -> None:
    assert _script_write_denied(command, tmp_path)


@pytest.mark.parametrize(
    ("command", "protected_file"),
    [
        pytest.param(
            "python -c 'from pathlib import Path; Path(\"Makefile\").write_text(\"x\")'",
            "Makefile",
            id="python_makefile_write_text",
        ),
        pytest.param(
            "python -c 'from pathlib import Path; "
            'Path("Dockerfile").write_bytes(b"x")\'',
            "Dockerfile",
            id="python_dockerfile_write_bytes",
        ),
        pytest.param(
            "node -e 'require(\"fs\").writeFileSync(\"Makefile\", \"x\")'",
            "Makefile",
            id="node_makefile_write_file_sync",
        ),
    ],
)
def test_script_mutations_to_extensionless_protected_paths_are_denied(
    command: str, protected_file: str, tmp_path: Path
) -> None:
    assert _protected_script_write_denied(command, protected_file, tmp_path)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("./bin/find . -name x -delete", id="path_find_delete"),
        pytest.param("env ./bin/find . -name x -delete", id="wrapped_path_find"),
    ],
)
def test_path_qualified_find_mutations_are_not_safe_reads(
    command: str, tmp_path: Path
) -> None:
    assert _mutating_shell_not_safe_read(command, tmp_path)


def test_subprocess_call_string_mutation_to_slopgate_toml_is_denied(
    tmp_path: Path,
) -> None:
    command = (
        "python -c 'import subprocess; "
        'subprocess.call("touch slopgate.toml", shell=True)\''
    )

    assert _script_write_denied(command, tmp_path)


def test_interpreter_read_slopgate_toml_does_not_emit_edit_only_denials(
    tmp_path: Path,
) -> None:
    assert _interpreter_read_allowed(tmp_path)


@pytest.mark.parametrize(
    ("command", "expected_intent", "expected_source"),
    [
        pytest.param(
            "rtk read slopgate.toml",
            "read",
            "command_args",
            id="safe_rtk_read",
        ),
        pytest.param(
            "printf x > slopgate.toml",
            "mutate",
            "redirect_target",
            id="redirect_mutation",
        ),
        pytest.param(
            "python -c 'from pathlib import Path; "
            'Path("slopgate.toml").write_text("x")\'',
            "mutate",
            "script_write_target",
            id="interpreter_write",
        ),
        pytest.param(
            "python -c 'print(open(\"slopgate.toml\").read())'",
            "execute",
            "command_text",
            id="interpreter_read",
        ),
    ],
)
def test_shell_intent_candidate_path_source_telemetry(
    command: str, expected_intent: str, expected_source: str, tmp_path: Path
) -> None:
    assert _shell_telemetry_matches(
        command, expected_intent, expected_source, tmp_path
    )
