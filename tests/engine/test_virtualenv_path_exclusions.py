from __future__ import annotations

from pathlib import Path

from vibeforcer.engine import evaluate_payload

from tests.support import finding_ids


def _write_quality_gate(repo: Path) -> Path:
    repo.mkdir(parents=True)
    _ = (repo / "quality_gate.toml").write_text(
        "[quality_gate]\nenabled = true\n", encoding="utf-8"
    )
    return repo


def test_post_edit_lint_rule_skips_virtualenv_lib_inspection(tmp_path: Path) -> None:
    repo = _write_quality_gate(tmp_path / "repo_lint_virtualenv")
    target = (
        tmp_path
        / ".venvs"
        / "job-hunter"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "textual"
        / "app.py"
    )
    target.parent.mkdir(parents=True)
    _ = target.write_text(
        "def noisy(a, b, c, d, e, f, g):\n"
        "    return a + b + c + d + e + f + g\n",
        encoding="utf-8",
    )
    payload = {
        "session_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": f"cat {target}"},
    }

    result = evaluate_payload(payload)

    assert "QUALITY-LINT-001" not in finding_ids(result)


def test_python_ast_parse_failure_skips_dot_venvs_paths(tmp_path: Path) -> None:
    repo = _write_quality_gate(tmp_path / "repo_ast_virtualenv")
    path_value = ".venvs/job-hunter/lib/python3.12/site-packages/pkg/bad.py"
    payload = {
        "session_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path_value, "content": "def broken(:\n"},
    }

    result = evaluate_payload(payload)

    assert "PY-AST-001" not in finding_ids(result)
