from __future__ import annotations

__all__ = [
    "Path",
    "evaluate_payload",
    "EngineResult",
    "_repo_with_touched_source_coverage",
    "_evaluate_post_edit_lint_for_touched_source",
]


from pathlib import Path

from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult


def _repo_with_touched_source_coverage(tmp_path: Path) -> Path:
    repo = tmp_path / "repo_lint_static_refs"
    src_dir = repo / "src" / "pkg"
    tests_dir = repo / "tests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    _ = (repo / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    _ = (src_dir / "__init__.py").write_text("", encoding="utf-8")
    _ = (src_dir / "config.py").write_text(
        "class SessionConfig:\n    pass\n",
        encoding="utf-8",
    )
    _ = (tests_dir / "test_config.py").write_text(
        "from pkg.config import SessionConfig\n\n"
        "def test_config_reference():\n"
        "    assert SessionConfig() is not None\n",
        encoding="utf-8",
    )
    return repo


def _evaluate_post_edit_lint_for_touched_source(repo: Path) -> EngineResult:
    payload = {
        "session_id": "t",
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/pkg/config.py"},
        "tool_response": {"filePath": "src/pkg/config.py", "success": True},
    }
    return evaluate_payload(payload)
