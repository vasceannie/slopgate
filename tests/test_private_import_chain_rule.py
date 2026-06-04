from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from slopgate._types import object_dict, string_value
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult


def _permission_reason(result: EngineResult) -> str:
    assert result.output is not None, "expected hook output"
    spec = object_dict(result.output.get("hookSpecificOutput"))
    decision = string_value(spec.get("permissionDecision"))
    if decision is None:
        inner = object_dict(spec.get("decision"))
        return string_value(inner.get("message")) or ""
    return string_value(spec.get("permissionDecisionReason")) or ""


def _assert_denied_by(result: EngineResult, rule_id: str) -> None:
    reason = _permission_reason(result)
    assert rule_id in reason, f"expected {rule_id!r} in reason: {reason!r}"


def _rule_ids(result: EngineResult) -> set[str]:
    return {finding.rule_id for finding in result.findings}


class TestPrivateImportChainRule(unittest.TestCase):
    def _payload(self, path: str, content: str) -> dict[str, object]:
        return {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": content},
            "cwd": str(Path(__file__).resolve().parents[1]),
        }

    def test_stacked_private_import_chain_is_denied(self) -> None:
        result = evaluate_payload(
            self._payload(
                "src/cli/auth/runner.py",
                "from src.cli.auth._orchestrate._core import _AuthCtx\n",
            )
        )

        _assert_denied_by(result, "PY-IMPORT-003")
        assert "PY-IMPORT-003" in _rule_ids(result), (
            "stacked private import chains should be denied"
        )

    def test_stacked_private_module_path_is_denied(self) -> None:
        result = evaluate_payload(
            self._payload("src/cli/auth/_orchestrate/_core.py", "VALUE = 1\n")
        )

        _assert_denied_by(result, "PY-IMPORT-003")
        assert "PY-IMPORT-003" in _rule_ids(result), (
            "stacked private package paths should be denied"
        )

    def test_single_private_segment_remains_allowed(self) -> None:
        result = evaluate_payload(
            self._payload(
                "src/cli/auth/runner.py",
                "from src.cli.auth._types import AuthResult\n",
            )
        )

        assert "PY-IMPORT-003" not in _rule_ids(result)

    def test_public_descriptive_package_split_remains_allowed(self) -> None:
        result = evaluate_payload(
            self._payload(
                "src/cli/auth/orchestrate/core.py",
                "from src.cli.auth.orchestrate.context import AuthCtx\n",
            )
        )

        assert "PY-IMPORT-003" not in _rule_ids(result)

    def test_posttool_existing_stacked_private_file_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            repo = Path(tmp_dir) / "repo"
            target = repo / "src/cli/auth/_orchestrate/_core.py"
            target.parent.mkdir(parents=True)
            _ = (repo / "slopgate.toml").write_text(
                "[slopgate]\nenabled = true\n",
                encoding="utf-8",
            )
            _ = target.write_text("VALUE = 1\n", encoding="utf-8")
            payload = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "src/cli/auth/_orchestrate/_core.py"},
                "cwd": str(repo),
            }

            result = evaluate_payload(payload)

        assert "PY-IMPORT-003" in _rule_ids(result)


if __name__ == "__main__":
    _ = unittest.main()
