from __future__ import annotations

from tests.test_ast_rules import (
    BUNDLE_ROOT,
    ObjectDict,
    _assert_denied_by,
    _assert_not_denied,
    _permission_reason,
    evaluate_payload,
    unittest,
)

class TestImportAliasGuard(unittest.TestCase):
    def _make_payload(self, code: str, *, tool_name: str = "Write") -> ObjectDict:
        tool_input = {"file_path": "src/main.py", "content": code}
        if tool_name == "Patch":
            tool_input = {"patch": code}
        return {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": str(BUNDLE_ROOT),
        }

    def test_nonstandard_module_import_alias_denied(self) -> None:
        code = "import app.shared.normalizers as normalizers_v2\n"
        result = evaluate_payload(self._make_payload(code))
        assert any(f.rule_id == "PY-IMPORT-002" for f in result.findings)
        _assert_denied_by(result, "PY-IMPORT-002")

    def test_nonstandard_from_import_alias_denied(self) -> None:
        code = "from app.shared.normalizers import normalize_user as normalize_order\n"
        result = evaluate_payload(self._make_payload(code))
        assert any(f.rule_id == "PY-IMPORT-002" for f in result.findings)
        _assert_denied_by(result, "PY-IMPORT-002")

    def test_nonstandard_import_alias_gives_exact_replacement(self) -> None:
        code = "from app.services import resolver as r\n"
        result = evaluate_payload(self._make_payload(code))
        _assert_denied_by(result, "PY-IMPORT-002")
        reason = _permission_reason(result)

        assert "from app.services import resolver" in reason
        assert "resolver.<name>(...)" in reason

    def test_allowed_scientific_library_aliases_not_denied(self) -> None:
        code = "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "import polars as pl",
                "from matplotlib import pyplot as plt",
                "import seaborn as sns",
                "",
            ]
        )
        result = evaluate_payload(self._make_payload(code))
        _assert_not_denied(result)
        rule_ids = {f.rule_id for f in result.findings}
        assert "PY-IMPORT-002" not in rule_ids, "canonical aliases must remain allowed"

    def test_patch_added_nonstandard_import_alias_denied(self) -> None:
        patch_text = (
            "*** Begin Patch\n"
            "*** Add File: src/aliased.py\n"
            "+import app.shared as shared2\n"
            "+\n"
            "+def load(value: object) -> object:\n"
            "+    loaded = shared2.load(value)\n"
            "+    return {\"loaded\": loaded}\n"
            "*** End Patch\n"
        )
        result = evaluate_payload(self._make_payload(patch_text, tool_name="Patch"))
        assert any(f.rule_id == "PY-IMPORT-002" for f in result.findings)
        _assert_denied_by(result, "PY-IMPORT-002")

class TestImportFanout(unittest.TestCase):
    def _make_payload(self, code: str) -> ObjectDict:
        return {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": code},
            "cwd": str(BUNDLE_ROOT),
        }

    def test_at_threshold_ok(self) -> None:
        """Exactly 5 imports from one module -- at threshold, not flagged."""
        code = "from mymodule import a, b, c, d, e"
        result = evaluate_payload(self._make_payload(code))
        _assert_not_denied(result)
        rule_ids = {f.rule_id for f in result.findings}
        assert "PY-IMPORT-001" not in rule_ids, "at-threshold import must not be flagged"

    def test_over_threshold_context_only(self) -> None:
        """6 imports from one module -- fires context finding, does NOT deny."""
        code = "from mymodule import a, b, c, d, e, f"
        result = evaluate_payload(self._make_payload(code))
        _assert_not_denied(result)
        rule_ids = {f.rule_id for f in result.findings}
        assert "PY-IMPORT-001" in rule_ids, "over-threshold import must fire PY-IMPORT-001"

    def test_family_prefix_detected(self) -> None:
        """Shared parse_ prefix family elevates severity to MEDIUM."""
        from vibeforcer.models import Severity

        code = (
            "from myparser import "
            "parse_user, parse_order, parse_product, "
            "parse_invoice, parse_shipment, parse_address"
        )
        result = evaluate_payload(self._make_payload(code))
        _assert_not_denied(result)
        fanout_findings = [f for f in result.findings if f.rule_id == "PY-IMPORT-001"]
        assert len(fanout_findings) > 0, "family prefix must produce PY-IMPORT-001 finding"
        assert fanout_findings[0].severity == Severity.MEDIUM, (
            "family prefix must elevate severity to MEDIUM"
        )

    def test_bare_import_not_flagged(self) -> None:
        """import module (not from-import) is never flagged."""
        code = "import os\nimport sys\nimport json\nimport re\nimport ast\nimport abc"
        result = evaluate_payload(self._make_payload(code))
        rule_ids = {f.rule_id for f in result.findings}
        assert "PY-IMPORT-001" not in rule_ids, "bare import must not trigger PY-IMPORT-001"

    def test_multiple_modules_each_under_threshold_ok(self) -> None:
        """Many imports spread across multiple modules -- each under threshold."""
        code = "\n".join(
            [
                "from mod_a import x, y, z",
                "from mod_b import p, q, r",
                "from mod_c import i, j, k",
            ]
        )
        result = evaluate_payload(self._make_payload(code))
        rule_ids = {f.rule_id for f in result.findings}
        assert "PY-IMPORT-001" not in rule_ids, (
            "imports spread across modules must not trigger PY-IMPORT-001"
        )
